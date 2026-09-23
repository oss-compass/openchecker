import unittest
from unittest.mock import patch

from openchecker.message_queue import consumer


class RabbitMQBlockedTimeoutTests(unittest.TestCase):
    def test_configured_milliseconds_are_passed_to_pika_as_seconds(self):
        config = {
            "host": "localhost",
            "port": "5672",
            "username": "guest",
            "password": "guest",
            "heartbeat_interval_s": "60",
            "blocked_connection_timeout_ms": "300000",
        }
        with patch("openchecker.message_queue.pika.ConnectionParameters") as parameters:
            with patch("openchecker.message_queue.pika.BlockingConnection", side_effect=KeyboardInterrupt):
                consumer(config, "opencheck", lambda *_: None)

        self.assertEqual(parameters.call_args.kwargs["blocked_connection_timeout"], 300)


if __name__ == "__main__":
    unittest.main()
