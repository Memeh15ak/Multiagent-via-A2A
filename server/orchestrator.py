# multi_agent_system/server/orchestrator.py - FIXED agent discovery

import asyncio
from typing import Dict, Any, List, Optional
from loguru import logger
import json
import httpx

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from config.settings import settings
from core.message_broker import message_broker
from protocols.message_types import InternalMessageType, UserQueryMessage, OrchestratorResponseMessage
from core.agent_registry import agent_registry
from protocols.a2a_protocol import a2a_protocol_handler
from core.base_agent import AgentResponse, AgentToolDefinition

class OrchestratorAgent:
    def __init__(self):
        self.orchestrator_agent: Optional[Agent] = None
        self.runner: Optional[Runner] = None
        self.session_service = InMemorySessionService()  # For managing ADK sessions
        self._is_initialized = False
        logger.info("OrchestratorAgent initialized (awaiting full setup).")

    async def initialize(self):
        if self._is_initialized:
            logger.info("OrchestratorAgent already initialized.")
            return

        logger.info("Initializing OrchestratorAgent with Google ADK and Perplexity AI...")

        # 1. Prepare tools from registered A2A agents
        adk_tools: List[FunctionTool] = []
        agent_configs = agent_registry.get_all_agent_configs()
        
        logger.info(f"Found {len(agent_configs)} agent configurations to process...")
        
        for agent_id, agent_config in agent_configs.items():
            logger.info(f"Processing agent: {agent_id} with config: {agent_config}")
            
            a2a_endpoint = agent_config.get("a2a_endpoint")
            if not a2a_endpoint:
                logger.warning(f"Agent config for {agent_id} missing 'a2a_endpoint'. Skipping ADK tool creation.")
                continue
                
            logger.info(f"Attempting to discover agent card for {agent_id} at {a2a_endpoint}")
            
            try:
                # CRITICAL FIX: Use proper discovery logic
                agent_card = await self._discover_agent_card_robust(a2a_endpoint, agent_id)
                
                if agent_card:
                    logger.info(f"Successfully discovered agent card for {agent_id}")
                    
                    # Generate ADK tool from agent card
                    tool_callable = await self._create_adk_tool_from_card(agent_card, agent_id, a2a_endpoint)
                    
                    if tool_callable:
                        logger.info(f"Successfully created tool callable for {agent_id}")
                        adk_tools.append(FunctionTool(tool_callable))
                        
                        # Register the agent
                        agent_registry.register_a2a_agent(
                            AgentToolDefinition(
                                name=agent_card.get("name", agent_id),
                                description=agent_card.get("description", "A2A Agent"),
                                parameters={},  # Will be filled from skills if available
                                a2a_endpoint=a2a_endpoint,
                                agent_id=agent_id
                            )
                        )
                        logger.info(f"Successfully registered agent tool for {agent_id}")
                    else:
                        logger.error(f"Failed to create ADK tool wrapper for agent: {agent_id}")
                else:
                    logger.warning(f"Could not discover AgentCard for {agent_id} at {a2a_endpoint}. Trying fallback approach...")
                    
                    # Fallback: Try to create a basic tool from agent config
                    await self._create_fallback_tool(agent_id, agent_config, adk_tools)
                    
            except Exception as e:
                logger.error(f"Exception while processing agent {agent_id}: {str(e)}")
                # Try fallback approach
                await self._create_fallback_tool(agent_id, agent_config, adk_tools)

        logger.info(f"Loaded {len(adk_tools)} ADK tools from A2A agent configurations.")

        # Add some basic tools if no tools were loaded
        if len(adk_tools) == 0:
            logger.warning("No tools loaded from A2A agents. Adding basic fallback tools...")
            adk_tools.extend(await self._create_basic_fallback_tools())

        # 2. Initialize the LLM for the orchestrator
        try:
            perplexity_llm = LiteLlm(
                api_key=settings.PERPLEXITY_API_KEY,
                model=settings.PERPLEXITY_MODEL,
                base_url=settings.PERPLEXITY_BASE_URL,
            )
            logger.info("Successfully initialized Perplexity LLM")
        except Exception as e:
            logger.error(f"Failed to initialize Perplexity LLM: {str(e)}")
            raise

        # 3. Create the Orchestrator Agent
        try:
            self.orchestrator_agent = Agent(
                name="Orchestrator",
                description="Central orchestrator agent delegating queries to sub-agents.",
                model=perplexity_llm,
                tools=adk_tools,
                instruction="""
                You are a helpful and intelligent orchestrator agent. Your primary role is to understand user queries
                and route them to the most appropriate specialized agent (tool) to get the answer.
                Use the provided tools carefully and return clear, concise answers.
                
                Available tools and their purposes:
                - Weather tools: For weather-related queries
                - Web search tools: For real-time web searches
                - News tools: For latest news and current events
                
                Always try to use the most appropriate tool for the user's query.
                """
            )
            logger.info(f"Successfully created Orchestrator Agent with {len(adk_tools)} tools")
        except Exception as e:
            logger.error(f"Failed to create Orchestrator Agent: {str(e)}")
            raise

        # 4. Create the Runner to execute the agent
        try:
            self.runner = Runner(
                agent=self.orchestrator_agent,
                app_name="main_orchestrator_app",
                session_service=self.session_service
            )
            logger.info("Successfully created Runner")
        except Exception as e:
            logger.error(f"Failed to create Runner: {str(e)}")
            raise

        self._is_initialized = True
        logger.info("OrchestratorAgent fully initialized and ready.")

    async def _discover_agent_card_robust(self, a2a_endpoint: str, agent_id: str) -> Optional[dict]:
        """
        Robust agent card discovery that handles both base URLs and /a2a endpoints
        """
        # Normalize the endpoint - remove trailing /a2a if present
        base_url = a2a_endpoint.rstrip('/a2a').rstrip('/')
        
        # List of discovery endpoints to try
        discovery_endpoints = [
            f"{base_url}/.well-known/agent.json",  # Standard A2A discovery
            f"{base_url}/agent-card",              # Alternative discovery
            f"{base_url}/info",                    # Info endpoint
            f"{base_url}/a2a",                     # A2A endpoint itself
            f"{base_url}/",                        # Root endpoint
        ]
        
        logger.info(f"Trying {len(discovery_endpoints)} discovery endpoints for {agent_id}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in discovery_endpoints:
                try:
                    logger.debug(f"Trying discovery endpoint: {endpoint}")
                    response = await client.get(endpoint)
                    
                    if response.status_code == 200:
                        try:
                            agent_card = response.json()
                            if self._validate_agent_card(agent_card):
                                logger.info(f"✅ Successfully discovered agent card for {agent_id} at {endpoint}")
                                return agent_card
                            else:
                                logger.debug(f"Invalid agent card format at {endpoint}")
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.debug(f"Failed to parse JSON response from {endpoint}: {e}")
                    else:
                        logger.debug(f"Discovery endpoint {endpoint} returned {response.status_code}")
                        
                except Exception as e:
                    logger.debug(f"Discovery failed for {endpoint}: {e}")
        
        logger.warning(f"Could not discover agent card at any endpoint for {agent_id}")
        return None

    def _validate_agent_card(self, agent_card: dict) -> bool:
        """Validate that the agent card has required fields"""
        required_fields = ["name", "description"]
        return all(field in agent_card for field in required_fields)

    async def _create_adk_tool_from_card(self, agent_card: dict, agent_id: str, a2a_endpoint: str):
        """Create an ADK tool callable from an agent card"""
        try:
            agent_name = agent_card.get("name", agent_id)
            agent_description = agent_card.get("description", "A2A Agent")
            
            # Create tool callable that handles A2A communication
            async def agent_tool_callable(query: str) -> str:
                """Tool that communicates with A2A agent"""
                try:
                    logger.info(f"Calling {agent_name} with query: {query}")
                    
                    # Prepare A2A task message
                    task_message = {
                        "message": {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": query
                            }
                        }
                    }
                    
                    # Make A2A call
                    result = await self._call_a2a_agent_direct(a2a_endpoint, task_message)
                    
                    if result:
                        return str(result)
                    else:
                        return f"No response from {agent_name}"
                        
                except Exception as e:
                    logger.error(f"Error calling {agent_name}: {e}")
                    return f"Error calling {agent_name}: {str(e)}"
            
            # Set function metadata for ADK
            agent_tool_callable.__name__ = f"{agent_id}_tool"
            agent_tool_callable.__doc__ = f"{agent_description} (Tool for {agent_name})"
            
            return agent_tool_callable
            
        except Exception as e:
            logger.error(f"Failed to create ADK tool from card for {agent_id}: {e}")
            return None

    async def _call_a2a_agent_direct(self, endpoint: str, task_message: dict) -> Optional[str]:
        """Direct A2A agent call"""
        try:
            # Ensure endpoint has /a2a if it doesn't already
            if not endpoint.endswith('/a2a'):
                a2a_url = f"{endpoint.rstrip('/')}/a2a"
            else:
                a2a_url = endpoint
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    a2a_url,
                    json=task_message,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Extract response from A2A format
                    if "artifacts" in result and result["artifacts"]:
                        artifact = result["artifacts"][0]
                        if "parts" in artifact and artifact["parts"]:
                            return artifact["parts"][0].get("text", "")
                    
                    # Fallback to direct response
                    return result.get("response", str(result))
                else:
                    logger.error(f"A2A call failed with status {response.status_code}: {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Direct A2A call failed: {e}")
            return None

    async def _create_fallback_tool(self, agent_id: str, agent_config: dict, adk_tools: List[FunctionTool]):
        """Create a fallback tool when agent card discovery fails"""
        try:
            logger.info(f"Creating fallback tool for {agent_id}")
            
            # Create a simple callable that uses the A2A endpoint directly
            async def fallback_tool_callable(query: str) -> str:
                """Fallback tool for when agent card discovery fails"""
                try:
                    task_message = {
                        "message": {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": query
                            }
                        }
                    }
                    
                    result = await self._call_a2a_agent_direct(
                        agent_config["a2a_endpoint"], 
                        task_message
                    )
                    
                    return result or f"No response from {agent_config.get('name', agent_id)}"
                    
                except Exception as e:
                    logger.error(f"Fallback tool call failed for {agent_id}: {str(e)}")
                    return f"Error calling {agent_config.get('name', agent_id)}: {str(e)}"
            
            # Set function metadata for ADK
            fallback_tool_callable.__name__ = f"{agent_id}_tool"
            fallback_tool_callable.__doc__ = f"{agent_config.get('description', 'Agent tool')}"
            
            adk_tools.append(FunctionTool(fallback_tool_callable))
            logger.info(f"Successfully created fallback tool for {agent_id}")
            
        except Exception as e:
            logger.error(f"Failed to create fallback tool for {agent_id}: {str(e)}")

    async def _create_basic_fallback_tools(self) -> List[FunctionTool]:
        """Create basic fallback tools if no A2A tools are available"""
        fallback_tools = []
        
        try:
            # Basic echo tool for testing
            async def echo_tool(message: str) -> str:
                """Simple echo tool for testing purposes"""
                return f"Echo: {message}"
            
            echo_tool.__name__ = "echo_tool"
            fallback_tools.append(FunctionTool(echo_tool))
            
            # Basic info tool
            async def info_tool() -> str:
                """Provides basic system information"""
                return "Orchestrator is running but no specialized tools are currently available."
            
            info_tool.__name__ = "info_tool"
            fallback_tools.append(FunctionTool(info_tool))
            
            logger.info(f"Created {len(fallback_tools)} basic fallback tools")
            
        except Exception as e:
            logger.error(f"Failed to create basic fallback tools: {str(e)}")
        
        return fallback_tools

    async def shutdown(self):
        logger.info("Shutting down OrchestratorAgent...")
        # clean shutdown logic if needed
        self.orchestrator_agent = None
        self.runner = None
        self._is_initialized = False

    async def handle_user_query(self, user_id: str, query: str):
        if not self._is_initialized:
            logger.error("OrchestratorAgent not initialized. Cannot handle user query.")
            return

        logger.info(f"Handling user query from {user_id}: {query}")
        
        try:
            session_id = f"session_{user_id}"
            response = await self.runner.run(input_text=query, session_id=session_id)

            logger.info(f"Orchestrator response: {response.output}")

            await message_broker.publish(
                InternalMessageType.ORCHESTRATOR_RESPONSE,
                OrchestratorResponseMessage(user_id=user_id, response=response.output).dict()
            )
        except Exception as e:
            logger.error(f"Error handling user query: {str(e)}")
            # Send error response
            await message_broker.publish(
                InternalMessageType.ORCHESTRATOR_RESPONSE,
                OrchestratorResponseMessage(
                    user_id=user_id, 
                    response=f"I encountered an error processing your request: {str(e)}"
                ).dict()
            )

# ✅ Instantiate orchestrator_agent at module level so it can be imported
orchestrator_agent = OrchestratorAgent()