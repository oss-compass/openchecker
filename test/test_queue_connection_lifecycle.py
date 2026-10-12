"""Short-lived queue operations must release their RabbitMQ connections."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pika

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openchecker"))
import message_queue


class Connection:
    # Exercise Pika's actual context-manager behavior without a live broker.
    __enter__ = pika.BlockingConnection.__enter__
    __exit__ = pika.BlockingConnection.__exit__

    def __init__(self, *channels):
        self.is_open = True
        self.channel = Mock(side_effect=channels)
        self.close = Mock(side_effect=self._close)

    def _close(self):
        self.is_open = False


class QueueConnectionLifecycleTests(unittest.TestCase):
    config = {"username": "test", "password": "test", "host": "localhost", "port": "5672"}

    def test_existing_queue_releases_connection(self):
        connection = Connection(Mock())
        with patch.object(pika, "BlockingConnection", return_value=connection):
            message_queue.create_queue(self.config, "tasks")
        connection.close.assert_called_once_with()

    def test_missing_queue_reuses_connection_with_new_channel(self):
        probe, create = Mock(), Mock()
        probe.queue_declare.side_effect = pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
        first, unexpected = Connection(probe, create), Connection(Mock())
        with patch.object(pika, "BlockingConnection", side_effect=[first, unexpected]) as connect:
            message_queue.create_queue(self.config, "tasks", {"x-message-ttl": 5000})
        self.assertEqual(connect.call_count, 1)
        create.queue_declare.assert_called_once_with(queue="tasks", arguments={"x-message-ttl": 5000})
        first.close.assert_called_once_with()

    def test_failed_queue_creation_releases_connection(self):
        probe, create = Mock(), Mock()
        probe.queue_declare.side_effect = pika.exceptions.ChannelClosedByBroker(404, "NOT_FOUND")
        create.queue_declare.side_effect = pika.exceptions.ChannelClosedByBroker(406, "PRECONDITION_FAILED")
        connection = Connection(probe, create)
        with patch.object(pika, "BlockingConnection", return_value=connection):
            try:
                message_queue.create_queue(self.config, "tasks")
            except (SystemExit, pika.exceptions.ChannelClosed):
                pass
        connection.close.assert_called_once_with()

    def test_access_denied_does_not_attempt_queue_creation(self):
        probe, create = Mock(), Mock()
        probe.queue_declare.side_effect = pika.exceptions.ChannelClosedByBroker(403, "ACCESS_REFUSED")
        connection = Connection(probe, create)
        with patch.object(pika, "BlockingConnection", return_value=connection):
            try:
                message_queue.create_queue(self.config, "tasks")
            except SystemExit:
                pass
        create.queue_declare.assert_not_called()
        connection.close.assert_called_once_with()

    def test_operation_errors_release_connections(self):
        cases = [
            (message_queue.publish_message, "basic_publish", ("payload",), "operation failed"),
            (message_queue.check_queue_status, "queue_declare", (), (None, None)),
            (message_queue.get_queue_info, "queue_declare", (), None),
            (message_queue.delete_queue, "queue_delete", (), None),
            (message_queue.purge_queue, "queue_purge", (), None),
        ]
        for operation, method, args, expected in cases:
            with self.subTest(operation=operation.__name__):
                channel = Mock()
                getattr(channel, method).side_effect = RuntimeError("operation failed")
                connection = Connection(channel)
                with patch.object(pika, "BlockingConnection", return_value=connection):
                    self.assertEqual(operation(self.config, "tasks", *args), expected)
                connection.close.assert_called_once_with()

    def test_channel_open_error_releases_connection(self):
        connection = Connection(RuntimeError("cannot open channel"))
        with patch.object(pika, "BlockingConnection", return_value=connection):
            self.assertEqual(message_queue.publish_message(self.config, "tasks", "payload"), "cannot open channel")
        connection.close.assert_called_once_with()

    def test_successful_operations_preserve_results(self):
        channel = Mock()
        channel.queue_declare.return_value.method = pika.spec.Queue.DeclareOk(
            queue="tasks", message_count=3, consumer_count=2
        )
        cases = [
            (message_queue.publish_message, ("payload",), None),
            (message_queue.check_queue_status, (), (3, 2)),
            (message_queue.delete_queue, (), None),
            (message_queue.purge_queue, (), None),
        ]
        for operation, args, expected in cases:
            with self.subTest(operation=operation.__name__):
                connection = Connection(channel)
                with patch.object(pika, "BlockingConnection", return_value=connection):
                    self.assertEqual(operation(self.config, "tasks", *args), expected)
                connection.close.assert_called_once_with()

    def test_queue_info_missing_arguments_releases_connection(self):
        channel = Mock()
        # AMQP's DeclareOk does not include queue arguments. Preserve the
        # existing error result while closing the connection on this path.
        channel.queue_declare.return_value.method = pika.spec.Queue.DeclareOk(
            queue="tasks", message_count=0, consumer_count=0
        )
        connection = Connection(channel)
        with patch.object(pika, "BlockingConnection", return_value=connection):
            self.assertIsNone(message_queue.get_queue_info(self.config, "tasks"))
        connection.close.assert_called_once_with()

    def test_connect_error_preserves_publish_error(self):
        with patch.object(pika, "BlockingConnection", side_effect=RuntimeError("offline")):
            self.assertEqual(message_queue.publish_message(self.config, "tasks", "payload"), "offline")


if __name__ == "__main__":
    unittest.main()
