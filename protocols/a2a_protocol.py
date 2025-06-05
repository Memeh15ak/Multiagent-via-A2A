# protocols/a2a_protocol.py

import asyncio
import httpx
from python_a2a import A2AClient, Message, TextContent, FunctionCallContent, FunctionResponseContent, MessageRole
from python_a2a.models import AgentCard
from typing import Dict, Any, Optional
from loguru import logger
from core.base_agent import AgentResponse, AgentToolDefinition
from core.agent_registry import agent_registry
from config.settings import settings
import json


class A2AProtocolHandler:
    def __init__(self):
        self._clients: Dict[str, A2AClient] = {}
        self._http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("A2AProtocolHandler initialized.")

    def get_client(self, agent_id: str, a2a_endpoint: str) -> A2AClient:
        if agent_id not in self._clients:
            self._clients[agent_id] = A2AClient(f"{a2a_endpoint}")
            logger.info(f"Created A2AClient for agent '{agent_id}' at {a2a_endpoint}")
        return self._clients[agent_id]

    async def discover_agent_card(self, a2a_endpoint: str, use_cache: bool = False, agent_id: Optional[str] = None) -> Optional[AgentCard]:
        """
        Discover an agent's capabilities by fetching its Agent Card.
        
        The A2A protocol specifies several possible discovery endpoints:
        1. /.well-known/agent.json (standard location)
        2. /a2a (direct A2A endpoint)
        3. /agent-card (alternative endpoint)
        """
        try:
            base_url = a2a_endpoint.rstrip('/')
            
            # List of possible agent card endpoints to try
            discovery_endpoints = [
                f"{base_url}/.well-known/agent.json",
                f"{base_url}/a2a",
                f"{base_url}/agent-card",
                f"{base_url}/info"
            ]
            
            agent_card = None
            
            # Try each endpoint until we find the agent card
            for endpoint in discovery_endpoints:
                try:
                    logger.debug(f"Attempting agent discovery at: {endpoint}")
                    response = await self._http_client.get(endpoint)
                    
                    if response.status_code == 200:
                        card_data = response.json()
                        
                        # Validate that this looks like an agent card
                        if self._is_valid_agent_card(card_data):
                            # Ensure the URL field is set correctly
                            if 'url' not in card_data or not card_data['url']:
                                card_data['url'] = base_url
                            
                            agent_card = AgentCard(**card_data)
                            logger.info(f"Successfully discovered agent card for '{agent_card.name}' at {endpoint}")
                            break
                        else:
                            logger.debug(f"Response from {endpoint} doesn't appear to be a valid agent card")
                            
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.debug(f"Endpoint {endpoint} not found (404), trying next endpoint")
                        continue
                    else:
                        logger.warning(f"HTTP error {e.response.status_code} at {endpoint}: {e.response.text}")
                        continue
                except json.JSONDecodeError:
                    logger.debug(f"Invalid JSON response from {endpoint}, trying next endpoint")
                    continue
                except Exception as e:
                    logger.debug(f"Error trying {endpoint}: {e}, trying next endpoint")
                    continue
            
            if agent_card:
                return agent_card
            else:
                logger.warning(f"Could not discover agent card at any endpoint for {a2a_endpoint}")
                return None
                
        except httpx.RequestError as e:
            logger.error(f"Network error during agent discovery at {a2a_endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during agent discovery at {a2a_endpoint}: {e}", exc_info=True)
            return None

    def _is_valid_agent_card(self, data: Dict[str, Any]) -> bool:
        """
        Check if the response data looks like a valid agent card.
        An agent card should have at least name, description, and version.
        """
        required_fields = ['name', 'description']
        return all(field in data for field in required_fields)

    async def call_agent_tool(
        self,
        agent_tool_def: AgentToolDefinition,
        function_name: str,
        parameters: Dict[str, Any],
        conversation_id: Optional[str] = None,
        parent_message_id: Optional[str] = None
    ) -> AgentResponse:
        client = self.get_client(agent_tool_def.agent_id, agent_tool_def.a2a_endpoint)
        logger.info(f"Calling A2A agent '{agent_tool_def.name}' ({agent_tool_def.agent_id}) with function '{function_name}' and parameters: {parameters}")

        function_call_content = FunctionCallContent(
            name=function_name,
            parameters=parameters
        )

        message = Message(
            content=function_call_content,
            role=MessageRole.USER,
            conversation_id=conversation_id,
            parent_message_id=parent_message_id
        )

        try:
            response_message = await client.send_message(message)

            if isinstance(response_message.content, TextContent):
                logger.info(f"Received text response from A2A agent '{agent_tool_def.name}': {response_message.content.text}")
                return AgentResponse(
                    status="success",
                    message="Function call executed, text response received.",
                    data={"response": response_message.content.text}
                )
            elif isinstance(response_message.content, FunctionResponseContent):
                logger.info(f"Received function response from A2A agent '{agent_tool_def.name}': {response_message.content.name}, {response_message.content.response}")
                return AgentResponse(
                    status="success",
                    message="Function call executed, function response received.",
                    data={"response": response_message.content.response, "function_name": response_message.content.name}
                )
            else:
                logger.warning(f"Received unexpected content type from A2A agent '{agent_tool_def.name}': {type(response_message.content)}")
                return AgentResponse(
                    status="error",
                    message=f"Unexpected content type received from agent: {type(response_message.content)}",
                    data={"raw_response": response_message.dict()}
                )

        except httpx.RequestError as e:
            logger.error(f"Network error calling A2A agent '{agent_tool_def.name}': {e}")
            return AgentResponse(
                status="error",
                message=f"Network error: {e}",
                data={"agent_id": agent_tool_def.agent_id, "function": function_name, "parameters": parameters}
            )
        except Exception as e:
            logger.error(f"Error communicating with A2A agent '{agent_tool_def.name}': {e}", exc_info=True)
            return AgentResponse(
                status="error",
                message=f"Internal agent communication error: {e}",
                data={"agent_id": agent_tool_def.agent_id, "function": function_name, "parameters": parameters}
            )

    def generate_adk_tool_from_a2a_card(self, agent_card: AgentCard, agent_id: str) -> Optional[Dict[str, Any]]:
        agent_config = agent_registry.get_agent_config(agent_id)
        if not agent_config or "tool_name" not in agent_config:
            logger.warning(f"Agent config or 'tool_name' missing for agent_id: {agent_id}. Cannot generate ADK tool.")
            return None

        adk_tool_name = agent_config["tool_name"]
        a2a_endpoint = agent_card.url

        def _run_async(coro):
            """Utility to safely run an async function from sync context."""
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                logger.error("Cannot run async call in an already running event loop.")
                return {"status": "error", "message": "Cannot run async function in existing event loop."}
            else:
                return asyncio.run(coro)

        def _tool_wrapper(**kwargs):
            _function_name = kwargs.pop("function_name", None)
            if not _function_name:
                logger.error(f"ADK tool '{adk_tool_name}' called without 'function_name'.")
                return {"status": "error", "message": "No function name provided."}

            _parameters = kwargs

            logger.debug(f"ADK tool wrapper for '{adk_tool_name}' invoking A2A agent '{agent_id}' function '{_function_name}' with {_parameters}")
            response = _run_async(
                self.call_agent_tool(
                    agent_tool_def=AgentToolDefinition(
                        name=agent_card.name,
                        description=agent_card.description,
                        parameters={},
                        a2a_endpoint=a2a_endpoint,
                        agent_id=agent_id
                    ),
                    function_name=_function_name,
                    parameters=_parameters
                )
            )
            return response.to_dict() if isinstance(response, AgentResponse) else response

        _tool_wrapper.__name__ = adk_tool_name
        _tool_wrapper.__doc__ = agent_card.description + \
            "\n\nAccepts arguments including `function_name` and parameters for the underlying A2A agent."

        return _tool_wrapper

    def agent_card_to_dict(self, agent_card: AgentCard) -> dict:
        return agent_card.dict()

    async def close(self):
        """Clean up resources."""
        await self._http_client.aclose()
        logger.info("A2AProtocolHandler closed.")


a2a_protocol_handler = A2AProtocolHandler()