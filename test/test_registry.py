import unittest
import datetime
from openchecker.agents.registry import AgentRegistry

class TestAgentRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = AgentRegistry()

    def test_register_agent(self):
        self.registry.register_agent("agent1", "Agent 1 description")
        agents = self.registry.get_agents()
        self.assertTrue("agent1" in agents)
        self.assertEqual(agents["agent1"]["info"], "Agent 1 description")
        self.assertEqual(agents["agent1"]["status"], "active")

    def test_update_status(self):
        self.registry.register_agent("agent2", "Agent 2 description")
        self.registry.update_status("agent2", "busy")
        agents = self.registry.get_agents()
        self.assertEqual(agents["agent2"]["status"], "busy")

    def test_get_agents(self):
        self.registry.register_agent("agent3", "Agent 3 description")
        agents = self.registry.get_agents()
        self.assertTrue("agent3" in agents)

    def test_get_agent_info(self):
        self.registry.register_agent("agent4", "Agent 4 description")
        info = self.registry.get_agent_info("agent4")
        self.assertEqual(info, "Agent 4 description")

    def test_get_agent_status(self):
        self.registry.register_agent("agent5", "Agent 5 description")
        status = self.registry.get_agent_status("agent5")
        self.assertEqual(status, "active")

    def test_remove_agent(self):
        self.registry.register_agent("agent6", "Agent 6 description")
        self.registry.remove_agent("agent6")
        agents = self.registry.get_agents()
        self.assertFalse("agent6" in agents)

if __name__ == '__main__':
    unittest.main()