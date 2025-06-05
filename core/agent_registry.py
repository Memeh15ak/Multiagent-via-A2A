# multi_agent_system/core/agent_registry.py

from typing import Dict, Optional, List
from core.base_agent import AgentToolDefinition
from loguru import logger
import yaml

class AgentRegistry:
    _instance = None
    _agents_configs: Dict[str, Dict] = {}
    _registered_a2a_agents: Dict[str, AgentToolDefinition] = {} # Tracks actively registered A2A agents

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentRegistry, cls).__new__(cls)
            cls._instance._load_agent_configs()
        return cls._instance

    def _load_agent_configs(self):
        # Load static agent configurations from agent_config.yaml
        config_path = "config/agent_config.yaml"
        try:
            with open(config_path, 'r') as f:
                self._agents_configs = yaml.safe_load(f).get('agents', {})
            logger.info(f"Loaded agent configurations from {config_path}")
        except FileNotFoundError:
            logger.error(f"Agent configuration file not found at {config_path}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing agent_config.yaml: {e}")

    def get_agent_config(self, agent_id: str) -> Optional[Dict]:
        return self._agents_configs.get(agent_id)

    def get_all_agent_configs(self) -> Dict[str, Dict]:
        return self._agents_configs

    def register_a2a_agent(self, agent_tool_def: AgentToolDefinition):
        """Registers a running A2A agent with its tool definition."""
        if agent_tool_def.agent_id in self._registered_a2a_agents:
            logger.warning(f"Agent '{agent_tool_def.name}' ({agent_tool_def.agent_id}) already registered. Updating.")
        self._registered_a2a_agents[agent_tool_def.agent_id] = agent_tool_def
        logger.info(f"Registered A2A agent: {agent_tool_def.name} ({agent_tool_def.agent_id}) at {agent_tool_def.a2a_endpoint}")

    def unregister_a2a_agent(self, agent_id: str):
        """Unregisters an A2A agent."""
        if agent_id in self._registered_a2a_agents:
            del self._registered_a2a_agents[agent_id]
            logger.info(f"Unregistered A2A agent: {agent_id}")
        else:
            logger.warning(f"Attempted to unregister unknown A2A agent: {agent_id}")

    def get_registered_a2a_agents(self) -> Dict[str, AgentToolDefinition]:
        """Returns all currently registered A2A agents."""
        return self._registered_a2a_agents

    def get_a2a_tool_definition(self, tool_name: str) -> Optional[AgentToolDefinition]:
        """Finds an A2A tool definition by its given tool_name (from agent_config)."""
        for agent_id, agent_def in self._registered_a2a_agents.items():
            # Match the tool_name from agent_config.yaml to the registered agent's tool_name
            config = self.get_agent_config(agent_id)
            if config and config.get("tool_name") == tool_name:
                return agent_def
        return None

# Singleton instance
agent_registry = AgentRegistry()