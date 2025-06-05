# multi_agent_system/server/api_gateway.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional
from loguru import logger
import asyncio
import json
import time

from protocols.message_types import UserQueryMessage, OrchestratorResponseMessage, InternalMessageType
from core.message_broker import message_broker
from server.websocket_handler import websocket_manager # To send response back via WebSocket

router = APIRouter()

class QueryRequest(BaseModel):
    user_id: str
    query: str

class QueryResponse(BaseModel):
    query_id: str
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None

# Global variable to track the listener task
_websocket_listener_task: Optional[asyncio.Task] = None
_listener_running = False

@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Receives a user query via REST API, passes it to the orchestrator via MessageBroker,
    and returns an acknowledgment. The actual response will come via WebSocket.
    """
    logger.info(f"Received API query from user '{request.user_id}': {request.query}")

    user_query_message = UserQueryMessage(user_id=request.user_id, text_content=request.query)

    try:
        # Publish the query to the message broker for the orchestrator to pick up
        await message_broker.publish(InternalMessageType.USER_QUERY, user_query_message.dict())

        # For REST API, we acknowledge receipt immediately.
        # The actual response will be sent via WebSocket.
        return QueryResponse(
            query_id=user_query_message.query_id,
            status="accepted",
            message="Query received. Response will be sent via WebSocket."
        )
    except Exception as e:
        logger.error(f"Error publishing query to message broker: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process query: {e}")

# FIXED: This background task now properly consumes messages using async for
async def _websocket_response_listener():
    """
    Listens for orchestrator responses from the MessageBroker and sends them
    to the appropriate WebSocket client.
    """
    global _listener_running
    _listener_running = True
    
    logger.info("WebSocket response listener started.")
    
    try:
        # FIXED: Use async for to iterate over the async generator
        async for response_dict in message_broker.consume(InternalMessageType.ORCHESTRATOR_RESPONSE):
            if not _listener_running:
                logger.info("Listener stopping due to shutdown signal")
                break
                
            try:
                response_message = OrchestratorResponseMessage.parse_obj(response_dict)

                logger.info(f"Received orchestrator response for query {response_message.query_id} (User ID: {response_message.user_id})")

                # Find the WebSocket connection for the user_id and send the response
                # Assuming one WebSocket per user for simplicity in this demo.
                await websocket_manager.send_message_to_user(
                    user_id=response_message.user_id,
                    message={
                        "sender": "orchestrator",
                        "content": response_message.response_content,
                        "query_id": response_message.query_id,
                        "agent_used": response_message.agent_used,
                        "is_final": response_message.is_final,
                        "timestamp": time.time()
                    }
                )

            except Exception as e:
                logger.error(f"Error processing orchestrator response: {e}", exc_info=True)
                
    except asyncio.CancelledError:
        logger.info("WebSocket response listener cancelled")
    except Exception as e:
        logger.error(f"Error in WebSocket response listener: {e}", exc_info=True)
    finally:
        _listener_running = False
        logger.info("WebSocket response listener stopped")

# Alternative implementation using consume_one for better control
async def _websocket_response_listener_alternative():
    """
    Alternative implementation using consume_one method for more control over message consumption.
    """
    global _listener_running
    _listener_running = True
    
    logger.info("WebSocket response listener (alternative) started.")
    
    try:
        while _listener_running:
            try:
                # Use consume_one with timeout
                response_dict = await message_broker.consume_one(
                    InternalMessageType.ORCHESTRATOR_RESPONSE, 
                    timeout=1.0
                )
                
                if response_dict:
                    try:
                        response_message = OrchestratorResponseMessage.parse_obj(response_dict)

                        logger.info(f"Received orchestrator response for query {response_message.query_id} (User ID: {response_message.user_id})")

                        # Send the response via WebSocket
                        await websocket_manager.send_message_to_user(
                            user_id=response_message.user_id,
                            message={
                                "sender": "orchestrator",
                                "content": response_message.response_content,
                                "query_id": response_message.query_id,
                                "agent_used": response_message.agent_used,
                                "is_final": response_message.is_final,
                                "timestamp": time.time()
                            }
                        )

                    except Exception as e:
                        logger.error(f"Error processing orchestrator response: {e}", exc_info=True)
                        
            except Exception as e:
                logger.error(f"Error in response listener loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)  # Brief pause on error
                
    except asyncio.CancelledError:
        logger.info("WebSocket response listener cancelled")
    except Exception as e:
        logger.error(f"Error in WebSocket response listener: {e}", exc_info=True)
    finally:
        _listener_running = False
        logger.info("WebSocket response listener stopped")

# Start the background listener when the server starts
@router.on_event("startup")
async def start_websocket_listener():
    global _websocket_listener_task
    
    if _websocket_listener_task is None or _websocket_listener_task.done():
        logger.info("Starting WebSocket response listener task")
        _websocket_listener_task = asyncio.create_task(_websocket_response_listener())
        
        # Optional: You can use the alternative implementation instead
        # _websocket_listener_task = asyncio.create_task(_websocket_response_listener_alternative())
    else:
        logger.warning("WebSocket response listener task already running")

@router.on_event("shutdown")
async def stop_websocket_listener():
    global _websocket_listener_task, _listener_running
    
    logger.info("Stopping WebSocket response listener...")
    _listener_running = False
    
    if _websocket_listener_task and not _websocket_listener_task.done():
        _websocket_listener_task.cancel()
        try:
            await _websocket_listener_task
        except asyncio.CancelledError:
            logger.info("WebSocket listener task cancelled successfully")
        except Exception as e:
            logger.error(f"Error stopping WebSocket listener: {e}")

# Health check endpoint for the API gateway
@router.get("/health")
async def health_check():
    """Health check endpoint for the API gateway"""
    return {
        "status": "healthy",
        "websocket_listener_running": _listener_running,
        "websocket_listener_task_active": _websocket_listener_task is not None and not _websocket_listener_task.done(),
        "active_websocket_connections": len(websocket_manager.active_connections),
        "timestamp": time.time()
    }

@router.get("/status")
async def get_api_status():
    """Get detailed status of the API gateway"""
    return {
        "api_gateway_status": "running",
        "websocket_listener": {
            "running": _listener_running,
            "task_active": _websocket_listener_task is not None and not _websocket_listener_task.done(),
            "task_done": _websocket_listener_task.done() if _websocket_listener_task else True
        },
        "websocket_manager": {
            "active_connections": len(websocket_manager.active_connections),
            "user_ids": list(websocket_manager.active_connections.keys())
        },
        "message_broker_available": hasattr(message_broker, 'get_broker_stats'),
        "timestamp": time.time()
    }