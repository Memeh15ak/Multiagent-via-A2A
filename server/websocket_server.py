# server/websocket_server.py - Updated with proper message broker initialization

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import asyncio
import json
import time
from typing import Dict, Any, Optional
import uuid

from server.websocket_handler import websocket_manager

# Import core components
try:
    from core.message_broker import message_broker, InternalMessageType
    from core.query_handler import query_handler
    MESSAGE_BROKER_AVAILABLE = True
except ImportError:
    logger.warning("Message broker or query handler not available - running in minimal mode")
    MESSAGE_BROKER_AVAILABLE = False

# Try to import settings
try:
    from config.settings import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    logger.warning("Settings module not available - using defaults")
    SETTINGS_AVAILABLE = False
    class MinimalSettings:
        APP_NAME = "Multi-Agent Server"
        API_V1_STR = "/api/v1"
    settings = MinimalSettings()

# Try to import other optional modules
try:
    from server.api_gateway import router as api_router
    API_ROUTER_AVAILABLE = True
except ImportError:
    logger.warning("API router not available")
    API_ROUTER_AVAILABLE = False

# In-memory storage for query tracking
active_queries: Dict[str, Dict[str, Any]] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events for the FastAPI application."""
    logger.info(f"{settings.APP_NAME} starting up...")

    # Initialize message broker and query handler if available
    if MESSAGE_BROKER_AVAILABLE:
        try:
            # Start message broker first
            await message_broker.start()
            logger.info("Message broker started")
            
            # Start query handler (this will setup subscriptions)
            await query_handler.start()
            logger.info("Query handler started")
            
            # Setup additional broker subscriptions for WebSocket responses
            setup_broker_subscriptions()
            logger.info("Broker subscriptions configured")
            
        except Exception as e:
            logger.error(f"Error starting message broker/query handler: {e}")

    logger.info("Agent Server startup complete.")
    yield
    
    logger.info("Agent Server shutting down...")
    await websocket_manager.disconnect_all()
    
    # Shutdown message broker if available
    if MESSAGE_BROKER_AVAILABLE:
        try:
            await query_handler.stop()
            logger.info("Query handler stopped")
            await message_broker.stop()
            logger.info("Message broker stopped")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    logger.info("Agent Server shutdown complete.")

def setup_broker_subscriptions():
    """Setup message broker subscriptions for WebSocket responses"""
    if not MESSAGE_BROKER_AVAILABLE:
        return
        
    try:
        # Subscribe to query responses to relay them back to WebSocket connections
        message_broker.subscribe(
            InternalMessageType.QUERY_RESPONSE.value,
            handle_query_response_from_broker
        )
        logger.info("Subscribed to query responses from message broker")
    except Exception as e:
        logger.error(f"Failed to setup broker subscriptions: {e}")

async def handle_query_response_from_broker(message: Dict[str, Any]):
    """Handle query responses from the message broker"""
    try:
        query_id = message.get('query_id')
        user_id = message.get('user_id')
        response = message.get('response')
        status = message.get('status', 'completed')
        
        logger.info(f"Received broker response for query {query_id}, user {user_id}")
        
        # Update query status
        if query_id in active_queries:
            active_queries[query_id].update({
                "status": status,
                "end_time": time.time(),
                "response": response
            })
        
        # Find the WebSocket connection for this user
        websocket = websocket_manager.active_connections.get(user_id)
        if websocket:
            processing_time = (
                active_queries[query_id]["end_time"] - active_queries[query_id]["start_time"]
                if query_id in active_queries else 1.0
            )
            
            response_message = {
                "type": "query_response",
                "query_id": query_id,
                "response": response,
                "status": status,
                "processing_time": processing_time,
                "timestamp": time.time(),
                "agent_info": {
                    "agent_type": "message_broker_agent",
                    "confidence": 0.98,
                    "processing_agent": message.get('processing_agent', 'unknown')
                }
            }
            
            await websocket.send_text(json.dumps(response_message))
            logger.info(f"Sent broker response for query {query_id} to user {user_id}")
        else:
            logger.warning(f"No active WebSocket connection found for user {user_id}")
            
    except Exception as e:
        logger.error(f"Error handling query response from broker: {e}")

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

# Include API router if available
if API_ROUTER_AVAILABLE:
    app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def get_root():
    return {
        "message": "Multi-Agent WebSocket Server",
        "status": "running",
        "websocket_endpoint": "/ws",
        "health_endpoint": "/health",
        "active_connections": len(websocket_manager.active_connections),
        "message_broker_available": MESSAGE_BROKER_AVAILABLE,
        "timestamp": time.time()
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id = None
    try:
        user_id = await websocket_manager.connect(websocket)
        logger.info(f"WebSocket connected for user: {user_id}")
        
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket message from {user_id}: {data}")
            
            # Process message with proper error handling
            await process_websocket_message(data, user_id, websocket)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error for user {user_id}: {e}", exc_info=True)
    finally:
        if user_id:
            websocket_manager.disconnect(websocket)

async def process_websocket_message(data: str, user_id: str, websocket: WebSocket):
    """Process WebSocket messages with improved error handling"""
    try:
        # Handle plain text status requests
        if data.strip().lower() == "status":
            await handle_status_request(user_id, websocket)
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
        error_response = {
            "type": "error",
            "error": f"Server error: {str(e)}",
            "timestamp": time.time()
        }
        try:
            await websocket.send_text(json.dumps(error_response))
        except Exception as send_error:
            logger.error(f"Failed to send error response: {send_error}")

async def handle_json_message(message: dict, user_id: str, websocket: WebSocket):
    """Handle JSON formatted messages"""
    message_type = message.get("type", "unknown")
    
    if message_type == "query":
        await handle_query_message(message, user_id, websocket)
    elif message_type == "status":
        await handle_status_request(user_id, websocket)
    elif message_type == "ping":
        await handle_ping_message(message, websocket)
    else:
        error_response = {
            "type": "error",
            "error": f"Unknown message type: {message_type}",
            "timestamp": time.time()
        }
        await websocket.send_text(json.dumps(error_response))

async def handle_query_message(message: dict, user_id: str, websocket: WebSocket):
    """Handle query messages with proper message broker integration"""
    user_query = message.get("query")
    query_id = message.get("query_id", str(uuid.uuid4()))
    
    if not user_query:
        error_response = {
            "type": "error",
            "error": "Invalid message format. Expected 'query' field.",
            "timestamp": time.time()
        }
        await websocket.send_text(json.dumps(error_response))
        return
    
    # Store query info
    active_queries[query_id] = {
        "user_id": user_id,
        "query": user_query,
        "status": "processing",
        "start_time": time.time()
    }
    
    # Send acknowledgment
    acknowledgment = {
        "type": "query_received",
        "query_id": query_id,
        "status": "processing",
        "timestamp": time.time()
    }
    await websocket.send_text(json.dumps(acknowledgment))
    
    # Process the query asynchronously
    asyncio.create_task(process_query_async(websocket, query_id, user_query, user_id))

async def process_query_async(websocket: WebSocket, query_id: str, user_query: str, user_id: str):
    """Process query asynchronously with message broker integration"""
    try:
        # If message broker is available, use it for query processing
        if MESSAGE_BROKER_AVAILABLE:
            try:
                logger.info(f"Publishing query {query_id} to message broker")
                
                # Create proper message format for the broker
                query_message = {
                    'query_id': query_id,
                    'user_id': user_id,
                    'text_content': user_query,  # This is the key the query handler expects
                    'timestamp': time.time(),
                    'type': 'user_query'
                }
                
                # Publish query to message broker using the correct topic
                success = await message_broker.publish(
                    InternalMessageType.USER_QUERY.value, 
                    query_message
                )
                
                if success:
                    logger.info(f"Query {query_id} published to message broker successfully")
                    return
                else:
                    logger.warning(f"Failed to publish query {query_id} to message broker")
                
            except Exception as e:
                logger.warning(f"Message broker processing failed for query {query_id}, falling back to direct processing: {e}")
        
        # Fallback to direct processing if message broker is not available
        await process_query_directly(websocket, query_id, user_query, user_id)
        
    except Exception as e:
        logger.error(f"Error processing query {query_id}: {e}", exc_info=True)
        await send_query_error_response(websocket, query_id, str(e))

async def process_query_directly(websocket: WebSocket, query_id: str, user_query: str, user_id: str):
    """Process query directly without message broker"""
    try:
        logger.info(f"Processing query {query_id} directly")
        
        # Simulate processing time
        await asyncio.sleep(1)
        
        # Generate intelligent response
        response_text = generate_intelligent_response(user_query)
        
        # Update query status
        if query_id in active_queries:
            active_queries[query_id].update({
                "status": "completed",
                "end_time": time.time(),
                "response": response_text
            })
            processing_time = active_queries[query_id]["end_time"] - active_queries[query_id]["start_time"]
        else:
            processing_time = 1.0
        
        # Send response
        response_message = {
            "type": "query_response",
            "query_id": query_id,
            "query": user_query,
            "response": response_text,
            "status": "completed",
            "processing_time": processing_time,
            "timestamp": time.time(),
            "agent_info": {
                "agent_type": "direct_processor",
                "confidence": 0.95
            }
        }
        
        await websocket.send_text(json.dumps(response_message))
        logger.info(f"Sent direct response for query {query_id}")
        
    except Exception as e:
        logger.error(f"Error in direct processing for query {query_id}: {e}")
        await send_query_error_response(websocket, query_id, str(e))

async def send_query_error_response(websocket: WebSocket, query_id: str, error: str):
    """Send error response for a query"""
    try:
        # Update query status
        if query_id in active_queries:
            active_queries[query_id].update({
                "status": "error",
                "error": error,
                "end_time": time.time()
            })
        
        # Send error response
        error_response = {
            "type": "query_error",
            "query_id": query_id,
            "error": error,
            "timestamp": time.time()
        }
        
        await websocket.send_text(json.dumps(error_response))
        
    except Exception as send_error:
        logger.error(f"Failed to send error response for query {query_id}: {send_error}")

async def handle_status_request(user_id: str, websocket: WebSocket):
    """Handle status requests"""
    status_response = {
        "type": "status_response",
        "status": "running",
        "active_connections": len(websocket_manager.active_connections),
        "user_id": user_id,
        "active_queries": len([q for q in active_queries.values() if q.get("status") == "processing"]),
        "completed_queries": len([q for q in active_queries.values() if q.get("status") == "completed"]),
        "failed_queries": len([q for q in active_queries.values() if q.get("status") == "error"]),
        "total_queries": len(active_queries),
        "timestamp": time.time(),
        "server_info": {
            "name": "Multi-Agent WebSocket Server",
            "version": "1.0.0",
            "message_broker_available": MESSAGE_BROKER_AVAILABLE
        }
    }
    await websocket.send_text(json.dumps(status_response))

async def handle_ping_message(message: dict, websocket: WebSocket):
    """Handle ping messages"""
    # Update heartbeat for the user
    user_id = message.get("user_id")
    if user_id:
        websocket_manager.update_user_heartbeat(user_id)
    
    pong_response = {
        "type": "pong",
        "original_timestamp": message.get("timestamp"),
        "server_timestamp": time.time()
    }
    await websocket.send_text(json.dumps(pong_response))

async def handle_plain_text_message(text: str, user_id: str, websocket: WebSocket):
    """Handle plain text messages with query support"""
    logger.info(f"Processing plain text message from {user_id}: {text}")
    
    # Check if it's a query command (query<...>)
    if text.startswith('query<') and text.endswith('>'):
        query_text = text[6:-1]  # Extract text between query< and >
        query_id = f"plain_text_{int(time.time())}_{user_id}"
        
        # Create query message
        query_message = {
            "type": "query",
            "query": query_text,
            "query_id": query_id
        }
        
        # Process as query
        await handle_query_message(query_message, user_id, websocket)
        return
    
    # Generate contextual response for regular text
    response_text = generate_intelligent_response(text)
    
    response = {
        "type": "text_response",
        "original_message": text,
        "response": response_text,
        "user_id": user_id,
        "timestamp": time.time()
    }
    
    await websocket.send_text(json.dumps(response))

def generate_intelligent_response(query: str) -> str:
    """Generate contextual responses based on query content"""
    query_lower = query.lower().strip()
    
    # Remove any command prefixes
    if query_lower.startswith(('<', '>', '/')):
        query_lower = query_lower[1:].strip()
    
    # Weather queries
    if any(word in query_lower for word in ["weather", "temperature", "rain", "sunny", "cloudy"]):
        return (
            "🌤️ **Weather Information**: I understand you're asking about weather. "
            "While I don't have access to real-time weather data in this demo, "
            "I can help you process weather datasets or set up weather API integrations!"
        )
    
    # System queries
    elif any(word in query_lower for word in ["status", "health", "system"]):
        return (
            "✅ **System Status**: Multi-agent system is operational!\n"
            "• WebSocket connections: Active\n"
            "• Message broker: Running\n"
            "• Query processing: Available\n"
            "All systems are functioning normally."
        )
    
    # Default response
    else:
        return (
            f"🤖 **Processed**: I received your query: '{query}'\n\n"
            f"The multi-agent system has analyzed your request. For specific help, try asking about:\n"
            f"• Weather information\n"
            f"• System status\n"
            f"• Data analysis\n"
            f"• Programming assistance\n\n"
            f"What would you like to know more about?"
        )

# Health check endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_connections": len(websocket_manager.active_connections),
        "active_queries": len([q for q in active_queries.values() if q.get("status") == "processing"]),
        "total_queries": len(active_queries),
        "message_broker_available": MESSAGE_BROKER_AVAILABLE,
        "timestamp": time.time()
    }

@app.get("/status")
async def get_status():
    return {
        "status": "running",
        "active_connections": len(websocket_manager.active_connections),
        "user_ids": list(websocket_manager.active_connections.keys()),
        "queries": active_queries,
        "message_broker_available": MESSAGE_BROKER_AVAILABLE,
        "timestamp": time.time()
    }

@app.get("/queries")
async def get_query_status():
    """Get status of all queries"""
    return {
        "active_queries": len([q for q in active_queries.values() if q.get("status") == "processing"]),
        "completed_queries": len([q for q in active_queries.values() if q.get("status") == "completed"]),
        "failed_queries": len([q for q in active_queries.values() if q.get("status") == "error"]),
        "total_queries": len(active_queries),
        "queries": active_queries,
        "timestamp": time.time()
    }

@app.get("/broker/info")
async def get_broker_info():
    """Get message broker information"""
    if not MESSAGE_BROKER_AVAILABLE:
        return {"message": "Message broker not available"}
    
    try:
        broker_stats = message_broker.get_broker_stats()
        return {
            "message_broker_available": True,
            "broker_stats": broker_stats,
            "topics": message_broker.list_all_topics() if hasattr(message_broker, 'list_all_topics') else [],
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error getting broker info: {e}")
        return {
            "message_broker_available": True,
            "error": str(e),
            "timestamp": time.time()
        }