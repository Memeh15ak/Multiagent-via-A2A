# client/connection_manager.py

import asyncio
import json
import time
from typing import Optional, Dict, Any, Callable
from loguru import logger
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException


class ConnectionManager:
    def __init__(self, url: str):
        self.url = url
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.is_connected = False
        self.user_id: Optional[str] = None
        self.message_handlers: Dict[str, Callable] = {}
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.receive_task: Optional[asyncio.Task] = None
        self.connection_timeout = 10.0
        self.message_timeout = 30.0
        self.reconnect_delay = 5.0
        self.max_reconnect_attempts = 3
        self.reconnect_attempts = 0
        
        # Message queue for handling connection establishment
        self.connection_established_event = asyncio.Event()
        self.connection_established_data: Optional[Dict[str, Any]] = None
        
        # Add a flag to track if we're expecting connection_established
        self.expecting_connection_established = False
        
    async def connect(self) -> bool:
        """Connect to WebSocket server"""
        try:
            logger.info(f"Connecting to WebSocket server at {self.url}")
            
            # Reset connection established event
            self.connection_established_event.clear()
            self.connection_established_data = None
            self.expecting_connection_established = True
            
            # Connect with timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ),
                timeout=self.connection_timeout
            )
            
            logger.info("WebSocket connected successfully")
            
            # Start receiving messages BEFORE waiting for connection established
            self.receive_task = asyncio.create_task(self._receive_loop())
            
            # Wait a bit for initial messages
            await asyncio.sleep(0.5)
            
            # Try to wait for connection established message
            try:
                await asyncio.wait_for(
                    self.connection_established_event.wait(),
                    timeout=5.0
                )
                
                if self.connection_established_data:
                    self.user_id = self.connection_established_data.get("user_id")
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    logger.info(f"Connection established. User ID: {self.user_id}")
                    return True
                else:
                    logger.warning("Connection established event fired but no data received")
                    # Still consider it connected if websocket is open
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    return True
                    
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for connection established message")
                # Check if websocket is still open - if so, consider it connected
                if self.websocket and self._is_websocket_open():
                    logger.info("WebSocket is still open, proceeding without connection_established message")
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    self.expecting_connection_established = False
                    return True
                else:
                    logger.error("WebSocket connection lost during setup")
                    await self.disconnect()
                    return False
                
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout after {self.connection_timeout}s")
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}", exc_info=True)
            return False
    
    async def disconnect(self):
        """Disconnect from WebSocket server"""
        self.is_connected = False
        self.expecting_connection_established = False
        
        # Cancel tasks
        if self.receive_task and not self.receive_task.done():
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self.websocket = None
        
        self.user_id = None
        self.connection_established_event.clear()
        self.connection_established_data = None
        logger.info("WebSocket disconnected")
    
    async def send_json(self, message: Dict[str, Any]) -> bool:
        """Send JSON message"""
        if not self.is_connected or not self.websocket:
            logger.error("Cannot send message: not connected")
            return False
        
        try:
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent message: {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            await self._handle_connection_error()
            return False
    
    async def send_text(self, text: str) -> bool:
        """Send plain text message"""
        if not self.is_connected or not self.websocket:
            logger.error("Cannot send message: not connected")
            return False
        
        try:
            await self.websocket.send(text)
            logger.debug(f"Sent text: {text}")
            return True
        except Exception as e:
            logger.error(f"Failed to send text: {e}")
            await self._handle_connection_error()
            return False
    
    def add_message_handler(self, message_type: str, handler: Callable):
        """Add handler for specific message type"""
        self.message_handlers[message_type] = handler
    
    async def _receive_loop(self):
        """Main receive loop - this is the ONLY place that calls recv()"""
        try:
            while self.websocket and self._is_websocket_open():
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=self.message_timeout
                    )
                    
                    await self._handle_message(message)
                    
                except asyncio.TimeoutError:
                    logger.debug("No message received within timeout - sending ping")
                    await self._send_ping()
                    continue
                    
                except ConnectionClosed:
                    logger.info("WebSocket connection closed by server")
                    break
                    
                except Exception as e:
                    logger.error(f"Error in receive loop: {e}", exc_info=True)
                    break
                    
        except Exception as e:
            logger.error(f"Receive loop error: {e}", exc_info=True)
        finally:
            if self.is_connected:  # Only handle error if we were supposed to be connected
                await self._handle_connection_error()
    
    def _is_websocket_open(self) -> bool:
        """Check if websocket is open - compatible with different websockets versions"""
        if not self.websocket:
            return False
        
        try:
            # Try different attributes that might indicate connection state
            if hasattr(self.websocket, 'closed'):
                return not self.websocket.closed
            elif hasattr(self.websocket, 'state'):
                # For newer websockets versions
                from websockets.protocol import State
                return self.websocket.state == State.OPEN
            elif hasattr(self.websocket, 'open'):
                return self.websocket.open
            else:
                # Fallback - assume it's open if we have a websocket object
                return True
        except Exception:
            return False
    
    async def _handle_message(self, message: str):
        """Handle received message"""
        try:
            # Try to parse as JSON first
            try:
                data = json.loads(message)
                message_type = data.get("type", "unknown")
                
                logger.debug(f"Received JSON message type: {message_type}")
                
                # Handle built-in message types
                if message_type == "connection_established":
                    self.connection_established_data = data
                    self.connection_established_event.set()
                    self.expecting_connection_established = False
                    logger.debug("Connection established message handled")
                elif message_type == "heartbeat":
                    await self._handle_heartbeat(data)
                elif message_type == "welcome":
                    logger.info(f"Welcome message: {data.get('message')}")
                elif message_type == "pong":
                    logger.debug("Received pong")
                else:
                    # Handle with registered handlers
                    handler = self.message_handlers.get(message_type)
                    if handler:
                        await handler(data)
                    else:
                        logger.debug(f"No handler for message type: {message_type}")
                        
            except json.JSONDecodeError:
                # Handle as plain text
                logger.info(f"Received text message: {message}")
                
                # Check if this might be a connection established message in text format
                if self.expecting_connection_established and ("connected" in message.lower() or "established" in message.lower()):
                    logger.info("Detected connection established in text format")
                    self.connection_established_data = {"message": message}
                    self.connection_established_event.set()
                    self.expecting_connection_established = False
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def _handle_heartbeat(self, data: Dict[str, Any]):
        """Handle heartbeat from server"""
        logger.debug("Received heartbeat, sending response")
        await self.send_json({
            "type": "heartbeat_response",
            "timestamp": data.get("timestamp")
        })
    
    async def _send_ping(self):
        """Send ping to server"""
        if self.websocket and self._is_websocket_open():
            try:
                await self.send_json({
                    "type": "ping",
                    "timestamp": time.time()
                })
            except Exception as e:
                logger.warning(f"Failed to send ping: {e}")
    
    async def _handle_connection_error(self):
        """Handle connection errors and attempt reconnection"""
        if not self.is_connected:
            return
            
        self.is_connected = False
        logger.warning("Connection lost, attempting to reconnect...")
        
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            await asyncio.sleep(self.reconnect_delay)
            
            logger.info(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")
            success = await self.connect()
            
            if not success:
                logger.error(f"Reconnection attempt {self.reconnect_attempts} failed")
        else:
            logger.error("Maximum reconnection attempts reached")