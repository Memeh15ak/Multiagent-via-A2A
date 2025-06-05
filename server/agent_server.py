# server/agent_server.py - Fixed main server implementation

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import asyncio
import json
import time  # Use time instead of asyncio.time
from protocols.a2a_protocol import AgentCard

from config.settings import settings
from server.websocket_handler import websocket_manager
from server.api_gateway import router as api_router
from server.orchestrator import orchestrator_agent
from core.message_broker import message_broker
from protocols.message_types import InternalMessageType, UserQueryMessage
from core.agent_registry import agent_registry
from protocols.a2a_protocol import a2a_protocol_handler
import yaml

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    """
    logger.info(f"{settings.APP_NAME} starting up...")

    await orchestrator_agent.initialize()
    logger.info("Orchestrator Agent initialized.")

    for agent_id, agent_config in agent_registry.get_all_agent_configs().items():
        if "a2a_endpoint" in agent_config:
            try:
                agent_tool_def = a2a_protocol_handler.generate_adk_tool_from_a2a_card(
                    AgentCard(
                        name=agent_config.get("name", agent_id),
                        description=agent_config.get("description", "No description"),
                        url=agent_config["a2a_endpoint"],
                        version="0.1.0",
                        skills=[]
                    ),
                    agent_id=agent_id
                )
                if agent_tool_def:
                    logger.info(f"Registered A2A tool for agent: {agent_id}")
            except Exception as e:
                logger.error(f"Failed to register tool for agent {agent_id}: {e}")

    logger.info("Agent Server startup complete.")
    yield
    logger.info(f"{settings.APP_NAME} shutting down...")
    await websocket_manager.disconnect_all()
    await orchestrator_agent.shutdown()
    await message_broker.publish(
        InternalMessageType.AGENT_STATUS_UPDATE,
        {"status": "shutdown", "message": "Server is shutting down."}
    )
    logger.info("Agent Server shutdown complete.")

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def get_root():
    return HTMLResponse("<!-- your HTML content here -->")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id = await websocket_manager.connect(websocket)
    logger.info(f"WebSocket connected for user: {user_id}")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket message: {data}")
            
            # Handle the message with proper error handling
            await process_websocket_message(data, user_id, websocket)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error for user {user_id}: {e}", exc_info=True)
    finally:
        websocket_manager.disconnect(websocket)

async def process_websocket_message(data: str, user_id: str, websocket: WebSocket):
    """Process WebSocket messages with improved error handling"""
    try:
        # Handle plain text status requests
        if data.strip().lower() == "status":
            status_response = {
                "type": "status_response",
                "status": "running",
                "active_connections": len(websocket_manager.active_connections),
                "user_id": user_id,
                "timestamp": time.time()
            }
            await websocket.send_json(status_response)
            return
        
        # Try to parse as JSON
        try:
            message = json.loads(data)
            await handle_json_message(message, user_id, websocket)
        except json.JSONDecodeError:
            # Handle as plain text message
            await handle_plain_text_message(data, user_id, websocket)
            
    except Exception as e:
        logger.error(f"Error processing WebSocket message: {e}", exc_info=True)
        await websocket.send_json({
            "error": f"Server error: {str(e)}",
            "timestamp": time.time()
        })

async def handle_json_message(message: dict, user_id: str, websocket: WebSocket):
    """Handle JSON formatted messages"""
    message_type = message.get("type", "unknown")
    
    if message_type == "query":
        # Handle user queries
        user_query = message.get("query")
        query_id = message.get("query_id", "unknown")
        
        if user_query:
            # Send acknowledgment
            await websocket.send_json({
                "type": "query_received",
                "query_id": query_id,
                "status": "processing",
                "timestamp": time.time()
            })
            
            # Process with message broker
            query_message = UserQueryMessage(user_id=user_id, text_content=user_query)
            await message_broker.publish(
                InternalMessageType.USER_QUERY,
                query_message.dict()
            )
            
            # Send mock response for demo
            await asyncio.sleep(1)  # Simulate processing
            
            mock_response = generate_demo_response(user_query)
            await websocket.send_json({
                "type": "query_response",
                "query_id": query_id,
                "response": mock_response,
                "status": "completed",
                "timestamp": time.time()
            })
        else:
            await websocket.send_json({
                "error": "Invalid message format. Expected 'query' field.",
                "timestamp": time.time()
            })
    
    elif message_type == "ping":
        # Handle ping messages
        await websocket.send_json({
            "type": "pong",
            "timestamp": time.time()
        })
    
    else:
        await websocket.send_json({
            "error": f"Unknown message type: {message_type}",
            "timestamp": time.time()
        })

async def handle_plain_text_message(text: str, user_id: str, websocket: WebSocket):
    """Handle plain text messages"""
    logger.info(f"Processing plain text message from {user_id}: {text}")
    
    response = {
        "type": "text_response",
        "original_message": text,
        "response": f"Received your message: '{text}'",
        "user_id": user_id,
        "timestamp": time.time()
    }
    
    await websocket.send_json(response)

def generate_demo_response(query: str) -> str:
    """Generate demo responses based on query content"""
    query_lower = query.lower()
    
    if "weather" in query_lower:
        return ("Current weather conditions show partly cloudy skies with a temperature of 72°F. "
                "There's a 20% chance of light rain later today. Winds are light from the southwest.")
    
    elif "data analysis" in query_lower:
        return ("I can help you with various data analysis tasks including statistical analysis, "
                "data visualization, trend analysis, and predictive modeling. What specific type "
                "of analysis are you looking for?")
    
    elif any(greeting in query_lower for greeting in ["hello", "hi", "hey"]):
        return ("Hello! I'm your Multi-Agent System assistant. I'm here to help with queries "
                "about weather, data analysis, and more. What can I assist you with today?")
    
    else:
        return f"I processed your query: '{query}'. This is a demo response from the agent system."

# Health check endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_connections": len(websocket_manager.active_connections),
        "timestamp": time.time()
    }

@app.get("/status")
async def get_status():
    return {
        "status": "running",
        "active_connections": len(websocket_manager.active_connections),
        "user_ids": list(websocket_manager.active_connections.keys()),
        "timestamp": time.time()
    }