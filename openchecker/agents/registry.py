import datetime
import threading


class AgentRegistry:
    def __init__(self):
        self.agents = {}
        self.lock = threading.Lock()
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_thread = threading.Thread(target=self.check_heartbeats)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()

    def register_agent(self, agent_id, agent_info):
        with self.lock:
            self.agents[agent_id] = {
                'info': agent_info,
                'status': 'active',
                'last_update': datetime.datetime.now()
            }
            print(f"Agent {agent_id} registered.")

    def update_status(self, agent_id, status):
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]['status'] = status
                self.agents[agent_id]['last_update'] = datetime.datetime.now()
                print(f"Agent {agent_id} status updated to {status}.")
            else:
                print(f"Agent {agent_id} not found.")

    def get_agents(self):
        with self.lock:
            return self.agents.copy()

    def get_agent_info(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                return self.agents[agent_id]['info']
            else:
                print(f"Agent {agent_id} not found.")
                return None

    def get_agent_status(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                return self.agents[agent_id]['status']
            else:
                print(f"Agent {agent_id} not found.")
                return None

    def remove_agent(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                print(f"Agent {agent_id} removed.")
            else:
                print(f"Agent {agent_id} not found.")
                
    def set_agent_info(self, agent_id, new_info):
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]['info'] = new_info
                print(f"Agent {agent_id} info updated.")
            else:
                print(f"Agent {agent_id} not found.")

    def check_agent_activity(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                time_since_update = datetime.datetime.now() - self.agents[agent_id]['last_update']
                return time_since_update.total_seconds() < 60  # Consider agent active if updated within last 60 seconds
            else:
                print(f"Agent {agent_id} not found.")
                return False
            
    def receive_heartbeat(self, agent_id):
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]['last_update'] = datetime.datetime.now()
                if self.agents[agent_id]['status'] == 'inactive':
                    self.agents[agent_id]['status'] = 'active'
                print(f"Received heartbeat from Agent {agent_id}.")
            else:
                print(f"Agent {agent_id} not found.")

    def check_heartbeats(self):
        while True:
            with self.lock:
                for agent_id, agent_data in list(self.agents.items()):
                    time_since_update = datetime.datetime.now() - agent_data['last_update']
                    if time_since_update.total_seconds() > self.heartbeat_interval:
                        self.agents[agent_id]['status'] = 'inactive'
                        print(f"Agent {agent_id} is inactive due to missed heartbeats.")
            threading.Event().wait(self.heartbeat_interval)
                
if __name__ == "__main__":
    registry = AgentRegistry()

    registry.register_agent("agent1", "Agent 1 description")
    registry.register_agent("agent2", "Agent 2 description")

    agent1_info = registry.get_agent_info("agent1")
    print(f"Agent 1 Info: {agent1_info}")

    agent2_status = registry.get_agent_status("agent2")
    print(f"Agent 2 Status: {agent2_status}")

    registry.remove_agent("agent1")

    agents = registry.get_agents()
    for agent_id, agent_data in agents.items():
        print(f"Agent ID: {agent_id}, Info: {agent_data['info']}, Status: {agent_data['status']}, Last Update: {agent_data['last_update']}")
