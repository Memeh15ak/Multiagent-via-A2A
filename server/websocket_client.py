# websocket_client_fixed.py - Complete fix for WebSocket client

import asyncio
import json
import time
import websockets
from typing import Optional, Dict, Any, Callable
from loguru import logger

class WebSocketClient:
    def __init__(self, uri: str = "ws://localhost:5000/ws"):
        self.uri = uri
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.connected = False
        self.user_id: Optional[str] = None
        self.message_handlers: Dict[str, Callable] = {}
        self.running = False
        self.listen_task: Optional[asyncio.Task] = None
        self.last_ping_time = 0
        self.connection_stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "pings_received": 0,
            "pongs_sent": 0,
            "connection_time": 0
        }

    async def connect(self):
        """Connect to WebSocket server with proper configuration"""
        try:
            logger.info(f"Connecting to {self.uri}")
            
            # Connect with optimized settings for heartbeat handling
            self.websocket = await websockets.connect(
                self.uri,
                ping_interval=None,  # Disable built-in ping (we handle it manually)
                ping_timeout=None,   # Disable built-in timeout
                close_timeout=10,    # Wait 10 seconds for clean close
                max_size=1048576,    # 1MB max message size
                compression=None     # Disable compression for better performance
            )
            
            self.connected = True
            self.running = True
            self.connection_stats["connection_time"] = time.time()
            
            # Start listening for messages
            self.listen_task = asyncio.create_task(self._listen_for_messages())
            
            logger.info("✅ Connected to WebSocket server successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to WebSocket server: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """Gracefully disconnect from WebSocket server"""
        logger.info("🔌 Disconnecting from WebSocket server...")
        self.running = False
        
        # Cancel listening task
        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket connection
        if self.websocket and self.connected:
            try:
                await self.websocket.close()
                logger.info("✅ Disconnected gracefully")
            except Exception as e:
                logger.error(f"⚠️ Error during disconnect: {e}")
        
        self.connected = False
        self.websocket = None
        self.user_id = None

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Send message to server with error handling"""
        if not self.connected or not self.websocket:
            logger.error("❌ Not connected to server")
            return False
        
        try:
            message_str = json.dumps(message)
            await self.websocket.send(message_str)
            self.connection_stats["messages_sent"] += 1
            logger.debug(f"📤 Sent: {message}")
            return True
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("❌ Connection closed while sending message")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"❌ Error sending message: {e}")
            return False

    async def send_query(self, query: str, query_id: Optional[str] = None) -> tuple[bool, str]:
        """Send a query to the server"""
        if not query_id:
            query_id = f"query_{int(time.time() * 1000)}"
        
        message = {
            "type": "query",
            "query": query,
            "query_id": query_id,
            "timestamp": time.time()
        }
        
        success = await self.send_message(message)
        if success:
            logger.info(f"📝 Sent query: '{query}' (ID: {query_id})")
        return success, query_id

    async def send_plain_text_query(self, query: str) -> bool:
        """Send plain text query (like 'query<weather today>')"""
        formatted_query = f"query<{query}>"
        
        if not self.connected or not self.websocket:
            logger.error("❌ Not connected to server")
            return False
        
        try:
            await self.websocket.send(formatted_query)
            self.connection_stats["messages_sent"] += 1
            logger.info(f"📝 Sent plain text query: '{formatted_query}'")
            return True
        except Exception as e:
            logger.error(f"❌ Error sending plain text query: {e}")
            return False

    async def request_status(self) -> bool:
        """Request server status"""
        message = {
            "type": "status",
            "timestamp": time.time()
        }
        return await self.send_message(message)

    def add_message_handler(self, message_type: str, handler: Callable):
        """Add handler for specific message types"""
        self.message_handlers[message_type] = handler
        logger.debug(f"Added handler for message type: {message_type}")

    async def _listen_for_messages(self):
        """Listen for incoming messages from server"""
        logger.info("👂 Started listening for messages...")
        
        try:
            while self.running and self.connected and self.websocket:
                try:
                    # Wait for message with timeout to allow periodic checks
                    message_str = await asyncio.wait_for(
                        self.websocket.recv(), 
                        timeout=1.0
                    )
                    
                    self.connection_stats["messages_received"] += 1
                    await self._handle_message(message_str)
                    
                except asyncio.TimeoutError:
                    # This is normal - just continue listening
                    continue
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.info("🔌 WebSocket connection closed by server")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Error listening for messages: {e}")
        finally:
            self.connected = False
            logger.info("👂 Message listening stopped")

    async def _handle_message(self, message_str: str):
        """Handle incoming message with comprehensive type support"""
        try:
            message = json.loads(message_str)
            message_type = message.get("type", "unknown")
            
            logger.debug(f"📨 Received '{message_type}': {message}")
            
            # Handle all standard message types
            handlers = {
                "ping": self._handle_ping,
                "pong": self._handle_pong,
                "query_received": self._handle_query_received,
                "query_response": self._handle_query_response,
                "text_response": self._handle_text_response,
                "status_response": self._handle_status_response,
                "error": self._handle_error,
                "query_error": self._handle_query_error,
                "disconnect": self._handle_disconnect
            }
            
            # Call appropriate handler
            if message_type in handlers:
                await handlers[message_type](message)
            else:
                logger.warning(f"⚠️ Unknown message type: {message_type}")
            
            # Call custom handlers
            if message_type in self.message_handlers:
                await self._call_handler(self.message_handlers[message_type], message)
                
        except json.JSONDecodeError:
            logger.error(f"❌ Received invalid JSON: {message_str}")
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")

    async def _handle_ping(self, message: Dict[str, Any]):
        """Handle ping from server - CRITICAL for connection stability"""
        logger.debug("🏓 Received ping from server, sending pong...")
        
        # Extract user_id from ping if available
        user_id = message.get("user_id")
        if user_id and not self.user_id:
            self.user_id = user_id
            logger.info(f"🆔 Received user ID: {user_id}")
        
        # Send pong response immediately
        pong_message = {
            "type": "pong",
            "original_timestamp": message.get("timestamp"),
            "client_timestamp": time.time()
        }
        
        # Add user_id if we have it
        if self.user_id:
            pong_message["user_id"] = self.user_id
        
        success = await self.send_message(pong_message)
        if success:
            self.connection_stats["pings_received"] += 1
            self.connection_stats["pongs_sent"] += 1
            self.last_ping_time = time.time()
            logger.debug("✅ Pong sent successfully")
        else:
            logger.error("❌ Failed to send pong response")

    async def _handle_pong(self, message: Dict[str, Any]):
        """Handle pong from server"""
        original_timestamp = message.get("original_timestamp", 0)
        server_timestamp = message.get("server_timestamp", 0)
        current_time = time.time()
        
        if original_timestamp:
            round_trip_time = current_time - original_timestamp
            logger.debug(f"🏓 Pong received - RTT: {round_trip_time:.3f}s")

    async def _handle_query_received(self, message: Dict[str, Any]):
        """Handle query acknowledgment"""
        query_id = message.get("query_id")
        status = message.get("status", "unknown")
        logger.info(f"✅ Query {query_id} acknowledged - Status: {status}")

    async def _handle_query_response(self, message: Dict[str, Any]):
        """Handle query response"""
        query_id = message.get("query_id")
        response = message.get("response", "")
        status = message.get("status", "completed")
        processing_time = message.get("processing_time", 0)
        
        print(f"\n🤖 Query Response (ID: {query_id}):")
        print(f"📊 Status: {status}")
        print(f"⏱️ Processing Time: {processing_time:.2f}s")
        print(f"💬 Response:\n{response}\n")
        
        logger.info(f"✅ Query {query_id} completed in {processing_time:.2f}s")

    async def _handle_text_response(self, message: Dict[str, Any]):
        """Handle text response from server"""
        original_message = message.get("original_message", "")
        response = message.get("response", "")
        
        print(f"\n💬 Text Response:")
        print(f"📤 Original: {original_message}")
        print(f"📥 Response: {response}\n")

    async def _handle_status_response(self, message: Dict[str, Any]):
        """Handle status response"""
        status = message.get("status", "unknown")
        connections = message.get("active_connections", 0)
        server_info = message.get("server_info", {})
        
        print(f"\n📊 Server Status:")
        print(f"🟢 Status: {status}")
        print(f"👥 Active Connections: {connections}")
        print(f"🖥️ Server: {server_info.get('name', 'Unknown')}")
        print(f"📅 Version: {server_info.get('version', 'Unknown')}")
        print(f"🔧 Message Broker: {'Available' if server_info.get('message_broker_available') else 'Not Available'}\n")

    async def _handle_error(self, message: Dict[str, Any]):
        """Handle error message"""
        error = message.get("error", "Unknown error")
        query_id = message.get("query_id")
        
        if query_id:
            logger.error(f"❌ Query {query_id} failed: {error}")
        else:
            logger.error(f"❌ Server error: {error}")

    async def _handle_query_error(self, message: Dict[str, Any]):
        """Handle query-specific error"""
        query_id = message.get("query_id")
        error = message.get("error", "Unknown query error")
        logger.error(f"❌ Query {query_id} error: {error}")

    async def _handle_disconnect(self, message: Dict[str, Any]):
        """Handle disconnect message from server"""
        reason = message.get("reason", "unknown")
        logger.warning(f"🔌 Server requested disconnect: {reason}")
        await self.disconnect()

    async def _call_handler(self, handler: Callable, message: Dict[str, Any]):
        """Call message handler safely"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)
        except Exception as e:
            logger.error(f"❌ Error in custom message handler: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        current_time = time.time()
        stats = self.connection_stats.copy()
        
        if stats["connection_time"]:
            stats["uptime"] = current_time - stats["connection_time"]
            stats["uptime_formatted"] = f"{stats['uptime']:.1f}s"
        
        stats.update({
            "connected": self.connected,
            "user_id": self.user_id,
            "last_ping_time": self.last_ping_time,
            "seconds_since_last_ping": current_time - self.last_ping_time if self.last_ping_time else 0
        })
        
        return stats

    # Utility methods for testing
    async def wait_for_message_type(self, message_type: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Wait for a specific message type (useful for testing)"""
        result = {}
        event = asyncio.Event()
        
        async def temp_handler(message):
            result.update(message)
            event.set()
        
        old_handler = self.message_handlers.get(message_type)
        self.message_handlers[message_type] = temp_handler
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return None
        finally:
            if old_handler:
                self.message_handlers[message_type] = old_handler
            else:
                self.message_handlers.pop(message_type, None)


# Interactive client for testing
async def interactive_client():
    """Interactive WebSocket client for testing"""
    client = WebSocketClient("ws://127.0.0.1:5000/ws")
    
    # Connect to server
    if not await client.connect():
        print("❌ Failed to connect to server")
        return
    
    print("🚀 Connected! Type your commands:")
    print("Commands:")
    print("  weather <location> - Ask about weather")
    print("  status - Get server status")
    print("  stats - Get client statistics")
    print("  quit - Exit")
    print("-" * 50)
    
    try:
        while client.connected:
            try:
                # Get user input
                user_input = await asyncio.wait_for(
                    asyncio.to_thread(input, "> "), 
                    timeout=0.1
                )
                
                if user_input.lower() in ['quit', 'exit']:
                    break
                elif user_input.lower() == 'status':
                    await client.request_status()
                elif user_input.lower() == 'stats':
                    stats = client.get_stats()
                    print(f"\n📊 Client Stats: {json.dumps(stats, indent=2)}\n")
                elif user_input.startswith('weather '):
                    location = user_input[8:]
                    await client.send_plain_text_query(f"weather in {location}")
                elif user_input.strip():
                    await client.send_plain_text_query(user_input)
                    
            except asyncio.TimeoutError:
                # No input received, continue
                await asyncio.sleep(0.1)
                continue
                
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    finally:
        await client.disconnect()
        print("👋 Disconnected")


if __name__ == "__main__":
    # Run interactive client
    asyncio.run(interactive_client())