# multi_agent_system/tests/test_protocol.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from protocols.a2a_protocol import A2AProtocolHandler
from protocols.message_types import AgentResponse
from python_a2a.models import AgentCard, Skill, Parameter, Message, TextContent, FunctionCallContent, MessageRole

@pytest.fixture
def a2a_handler():
    return A2AProtocolHandler()

@pytest.mark.asyncio
async def test_discover_agent_card_success(a2a_handler):
    mock_client = AsyncMock()
    mock_client.discover.return_value = AgentCard(
        name="Mock Agent", description="Mock description", url="http://mock.com", version="1.0", skills=[]
    )
    with patch('protocols.a2a_protocol.A2AClient', return_value=mock_client):
        card = await a2a_handler.discover_agent_card("http://mock.com/a2a")
        assert card is not None
        assert card.name == "Mock Agent"

@pytest.mark.asyncio
async def test_call_agent_tool_success(a2a_handler):
    mock_client = AsyncMock()
    mock_client.send_message.return_value = Message(
        content=TextContent(text="Hello from mock agent"),
        role=MessageRole.AGENT
    )
    with patch('protocols.a2a_protocol.A2AClient', return_value=mock_client):
        response = await a2a_handler.call_agent_tool(
            agent_tool_def=MagicMock(agent_id="mock_agent_id", name="Mock Agent", a2a_endpoint="http://mock.com/a2a"),
            function_name="test_func",
            parameters={"arg": "value"}
        )
        assert isinstance(response, AgentResponse)
        assert response.status == "success"
        assert response.data["response"] == "Hello from mock agent"
        mock_client.send_message.assert_called_once()

# Add tests for error cases, different content types, etc.