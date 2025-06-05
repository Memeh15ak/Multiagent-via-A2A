# multi_agent_system/core/base_agent.py
# This file will define common utilities or abstract concepts that augment Google ADK agents,
# rather than defining a "BaseAgent" class that agents inherit from directly.
# Our agents will directly inherit from google.adk.agents.Agent.

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from loguru import logger

# A simple Pydantic model for structured responses from our agents
class AgentResponse(BaseModel):
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None

# Utility function for logging consistent messages
def log_agent_message(agent_name: str, level: str, message: str, **kwargs):
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(f"[{agent_name}]: {message}", **kwargs)

# This would represent a 'tool definition' that the orchestrator can use
# to understand what other agents can do. This will be primarily derived
# from the agent_config.yaml and ADK's internal tool representation.
class AgentToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] # OpenAPI-like schema for parameters
    a2a_endpoint: str
    agent_id: str