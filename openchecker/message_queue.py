import pika
from helper import read_config
import time
import threading
from logger import get_logger
import functools
from concurrent.futures import ThreadPoolExecutor


class ThreadSafeChannel:
    """
    Thread-safe Channel wrapper.
    Intercepts basic_ack and basic_nack calls, using connection.add_callback_threadsafe() to ensure thread safety.
    """
    def __init__(self, channel, connection):
        self._channel = channel
        self._connection = connection
    
    def basic_ack(self, delivery_tag, multiple=False):
        """Thread-safe message acknowledgment"""
        cb = functools.partial(
            self._channel.basic_ack,
            delivery_tag=delivery_tag,
            multiple=multiple
        )
        self._connection.add_callback_threadsafe(cb)
        logger.debug(f"Scheduled ACK for delivery_tag: {delivery_tag}")
    
    def basic_nack(self, delivery_tag, multiple=False, requeue=True):
        """Thread-safe message rejection"""
        cb = functools.partial(
            self._channel.basic_nack,
            delivery_tag=delivery_tag,
            multiple=multiple,
            requeue=requeue
        )
        self._connection.add_callback_threadsafe(cb)
        logger.debug(f"Scheduled NACK for delivery_tag: {delivery_tag}, requeue: {requeue}")
    
    def __getattr__(self, name):
        """Proxy other methods to the original channel"""
        return getattr(self._channel, name)

# Get logger for message queue module
logger = get_logger('openchecker.queue')

def create_queue(config, queue_name, arguments={}):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue = channel.queue_declare(queue=queue_name, arguments=arguments, passive=True)
        logger.info(f"Queue {queue_name} already exists, skipping creation")

    except pika.exceptions.ChannelClosed as e:
        logger.info(f"Queue {queue_name} does not exist, creating now")
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        queue = channel.queue_declare(queue=queue_name, arguments=arguments)
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
        exit()

    connection.close()

def publish_message(config, queue_name, message_body):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_publish(exchange='', routing_key=queue_name, body=message_body)
        connection.close()
        logger.info(f"Message published successfully")
        return None
    except Exception as e:
        logger.error(f"Message publishing failed: {e}")
        return str(e)

def consumer(config, queue_name, callback_func):
    """
    Consumer function that supports long-running tasks while maintaining heartbeat.
    
    Solution:
    1. Use thread pool to execute actual time-consuming tasks (callback_func)
    2. Main thread sends heartbeat periodically via connection.process_data_events()
    3. Use connection.add_callback_threadsafe() to ensure thread-safe message acknowledgment
    """
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(
        config['host'], 
        int(config['port']), 
        '/', 
        credentials, 
        heartbeat=int(config['heartbeat_interval_s']), 
        blocked_connection_timeout=float(config['blocked_connection_timeout_ms']) / 1000
    )
    
    # Create thread pool for executing time-consuming tasks
    executor = ThreadPoolExecutor(max_workers=1)

    def create_threaded_callback_wrapper(connection, channel):
        """Create a thread-safe callback wrapper"""
        # Create a thread-safe channel wrapper
        thread_safe_channel = ThreadSafeChannel(channel, connection)
        
        def threaded_callback_wrapper(ch, method, properties, body):
            """
            Wrapper callback function that executes actual tasks in thread pool.
            Passes thread-safe channel wrapper to ensure ACK/NACK operations are thread-safe.
            """
            def do_work():
                try:
                    # Pass thread-safe channel instead of original channel
                    callback_func(thread_safe_channel, method, properties, body)
                except Exception as e:
                    logger.error(f"Error in callback execution: {e}", exc_info=True)
                    # When exception occurs, use thread-safe way to NACK message
                    try:
                        thread_safe_channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        logger.warning(f"Message NACKed due to error: {method.delivery_tag}")
                    except Exception as nack_error:
                        logger.error(f"Failed to NACK message: {nack_error}")
            
            # Submit task to thread pool
            executor.submit(do_work)
            logger.debug(f"Task queued for delivery_tag: {method.delivery_tag}")
        
        return threaded_callback_wrapper

    while True:
        connection = None
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.basic_qos(prefetch_count=1)

            # Create wrapped callback for current connection and channel
            wrapped_callback = create_threaded_callback_wrapper(connection, channel)
            channel.basic_consume(queue=queue_name, on_message_callback=wrapped_callback, auto_ack=False)
            logger.info('Consumer connected, waiting for messages...')
            logger.info('Task execution mode: Serial (prefetch_count=1, max_workers=1, manual ACK)')
            
            # Periodically call process_data_events to handle heartbeat and message reception
            # This ensures heartbeat is sent normally even when callback executes for long time in worker thread
            while connection.is_open:
                connection.process_data_events(time_limit=1)  # Process events once per second

        except pika.exceptions.ConnectionClosedByBroker as e:
            logger.error(f"Broker closed connection: {e}")
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)
            continue

        except pika.exceptions.AMQPChannelError as e:
            logger.error(f"AMQP channel error: {e}")
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)
            continue

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"AMQP connection error: {e}")
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)
            continue

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break

        except Exception as e:
            logger.error(f"Consumer failed: {e}", exc_info=True)
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)
            continue

        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")
    
    # Shutdown thread pool
    executor.shutdown(wait=True)

def check_queue_status(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue_declaration = channel.queue_declare(queue=queue_name, passive=True)
        messages_in_queue = queue_declaration.method.message_count
        consumers_on_queue = queue_declaration.method.consumer_count

        connection.close()
        return messages_in_queue, consumers_on_queue
    except Exception as e:
        logger.info(f"Error checking queue status: {str(e)}")
        return None, None

def get_queue_info(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue_declaration = channel.queue_declare(queue=queue_name, passive=True)
        queue_arguments = queue_declaration.method.arguments

        connection.close()
        return queue_arguments
    except Exception as e:
        logger.info(f"Error getting queue info: {str(e)}")
        return None

def view_queue_logs(log_file_path):
    try:
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()
            queue_logs = [log for log in logs if "Queue" in log]
            return queue_logs
    except Exception as e:
        logger.info(f"Error viewing queue logs: {str(e)}")
        return None

def delete_queue(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_delete(queue=queue_name)
        connection.close()
        logger.info(f"Queue {queue_name} deleted successfully.")
    except Exception as e:
        logger.info(f"Error deleting queue {queue_name}: {str(e)}")

def purge_queue(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_purge(queue=queue_name)
        connection.close()
        logger.info(f"Queue {queue_name} purged successfully.")
    except Exception as e:
        logger.info(f"Error purging queue {queue_name}: {str(e)}")

def test_rabbitmq_connection(config):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        connection.close()
        logger.info("RabbitMQ connection successful.")
    except Exception as e:
        logger.info(f"Error connecting to RabbitMQ: {str(e)}")

if __name__ == "__main__":
    config = read_config('config/config.ini', "RabbitMQ")
    test_rabbitmq_connection(config)
