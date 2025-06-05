# multi_agent_system/protocols/message_types.py
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from uuid import uuid4
from enum import Enum
import time  # ← FIXED: Import time instead of asyncio for time functions

# Re-exporting A2A models for convenience if needed, though direct import is also fine
from python_a2a.models import Message, TextContent, FunctionCallContent, FunctionResponseContent, MessageRole

class InternalMessageType(str, Enum):
    """
    Defines internal message types for communication within our system
    (e.g., between API Gateway and Orchestrator).
    A2A messages handle agent-to-agent communication.
    """
    USER_QUERY = "user_query"
    ORCHESTRATOR_RESPONSE = "orchestrator_response"
    AGENT_STATUS_UPDATE = "agent_status_update"
    ERROR = "error"

class UserQueryMessage(BaseModel):
    """Message format for a user's query sent to the orchestrator."""
    query_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    text_content: str
    timestamp: float = Field(default_factory=lambda: time.time())  # ← FIXED: Use time.time()

class OrchestratorResponseMessage(BaseModel):
    """Message format for the orchestrator's response back to the client."""
    query_id: str
    user_id: str
    response_content: str
    agent_used: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: time.time())  # ← FIXED: Use time.time()
    is_final: bool = True  # Indicates if this is the final response or an intermediate one