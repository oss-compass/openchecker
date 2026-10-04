import datetime
import unittest
from unittest.mock import patch

from agents.registry import AgentRegistry


class HeartbeatRecoveryTests(unittest.TestCase):
    def setUp(self):
        # Run monitor iterations explicitly, without creating background threads.
        with patch('agents.registry.threading.Thread.start'):
            self.registry = AgentRegistry()
        self.registry.register_agent('worker', {'name': 'example'})

    def monitor_once(self):
        with patch('agents.registry.threading.Event') as event:
            event.return_value.wait.side_effect = StopIteration
            with self.assertRaises(StopIteration):
                self.registry.check_heartbeats()

    def test_heartbeat_recovers_worker_after_monitor_timeout(self):
        old = datetime.datetime.now() - datetime.timedelta(seconds=120)
        self.registry.agents['worker']['last_update'] = old
        self.monitor_once()
        self.assertEqual(self.registry.get_agent_status('worker'), 'inactive')
        self.registry.receive_heartbeat('worker')
        self.assertEqual(self.registry.get_agent_status('worker'), 'active')
        self.assertGreater(self.registry.agents['worker']['last_update'], old)
        self.assertTrue(self.registry.check_agent_activity('worker'))
        self.monitor_once()
        self.assertEqual(self.registry.get_agent_status('worker'), 'active')

    def test_busy_worker_keeps_its_operational_status(self):
        self.registry.update_status('worker', 'busy')
        self.registry.receive_heartbeat('worker')
        self.assertEqual(self.registry.get_agent_status('worker'), 'busy')

    def test_unknown_heartbeat_does_not_register_worker(self):
        self.registry.receive_heartbeat('unknown')
        self.assertNotIn('unknown', self.registry.get_agents())

    def test_active_worker_remains_active(self):
        self.registry.receive_heartbeat('worker')
        self.assertEqual(self.registry.get_agent_status('worker'), 'active')


if __name__ == '__main__':
    unittest.main()
