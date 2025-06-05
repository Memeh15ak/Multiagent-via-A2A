# client/agent_client.py

import asyncio
import json
import uuid
from typing import Dict, Any, Optional
from loguru import logger

from client.connection_manager import ConnectionManager


class AgentClient:
    def __init__(self, api_url: str = None, websocket_url: str = None):
        """
        Initialize AgentClient with backward compatibility
        
        Args:
            api_url: HTTP API URL (kept for backward compatibility, may be unused)
            websocket_url: WebSocket URL for real-time communication
        """
        # Handle different initialization patterns
        if websocket_url is None and api_url is not None:
            # If only one argument is provided, assume it's the websocket URL
            if api_url.startswith('ws://') or api_url.startswith('wss://'):
                self.websocket_url = api_url
                self.api_url = None
            else:
                # Convert HTTP URL to WebSocket URL
                self.api_url = api_url
                self.websocket_url = api_url.replace('http://', 'ws://').replace('https://', 'wss://').replace('/api/v1', '/ws')
        else:
            self.api_url = api_url
            self.websocket_url = websocket_url or "ws://127.0.0.1:5000/ws"
        
        logger.info(f"AgentClient initialized with WebSocket URL: {self.websocket_url}")
        if self.api_url:
            logger.info(f"API URL (for reference): {self.api_url}")
        
        self.connection_manager = ConnectionManager(self.websocket_url)
        self.user_id: Optional[str] = None
        self.is_running = False
        
        # Register message handlers
        self._setup_message_handlers()
    
    def _setup_message_handlers(self):
        """Setup message handlers for different message types"""
        self.connection_manager.add_message_handler("query_response", self._handle_query_response)
        self.connection_manager.add_message_handler("status", self._handle_status_response)
        self.connection_manager.add_message_handler("text_response", self._handle_text_response)
        self.connection_manager.add_message_handler("error", self._handle_error_response)
        self.connection_manager.add_message_handler("query_received", self._handle_query_received)
    
    async def connect(self) -> bool:
        """Connect to the multi-agent system"""
        logger.info("Attempting to connect to WebSocket server...")
        
        success = await self.connection_manager.connect()
        if success:
            self.user_id = self.connection_manager.user_id
            self.is_running = True
            logger.info(f"Client connected successfully. User ID: {self.user_id}")
            return True
        else:
            logger.error("Failed to connect to server")
            return False
    
    async def disconnect(self):
        """Disconnect from the server"""
        self.is_running = False
        await self.connection_manager.disconnect()
        logger.info("Client disconnected")
    
    async def send_query(self, query: str) -> Optional[str]:
        """Send a query to the agent system and wait for response"""
        if not self.connection_manager.is_connected:
            logger.error("Cannot send query: not connected")
            return None
        
        query_id = str(uuid.uuid4())
        
        message = {
            "type": "query",
            "query": query,
            "query_id": query_id,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        logger.info(f"Sending query: {query}")
        success = await self.connection_manager.send_json(message)
        
        if not success:
            logger.error("Failed to send query")
            return None
        
        return f"Query '{query}' sent with ID: {query_id}"
    
    async def send_text(self, text: str) -> bool:
        """Send plain text message"""
        if not self.connection_manager.is_connected:
            logger.error("Cannot send text: not connected")
            return False
        
        logger.info(f"Sending text: {text}")
        return await self.connection_manager.send_text(text)
    
    async def get_status(self):
        """Request server status"""
        if not self.connection_manager.is_connected:
            logger.error("Cannot get status: not connected")
            return
        
        logger.info("Requesting server status...")
        await self.connection_manager.send_text("status")
    
    # Backward compatibility methods
    async def start_listener(self):
        """Start listening for responses (backward compatibility)"""
        logger.info("Listener started (handled automatically by connection manager)")
        return True
    
    async def stop_listener(self):
        """Stop listening for responses (backward compatibility)"""
        logger.info("Stopping listener...")
        await self.disconnect()
    
    # Message handlers
    async def _handle_query_received(self, data: Dict[str, Any]):
        """Handle query received acknowledgment"""
        query_id = data.get("query_id")
        status = data.get("status")
        logger.info(f"Query {query_id} received by server - Status: {status}")
        print(f"⏳ Query received by server (ID: {query_id[:8]}...) - {status}")
    
    async def _handle_query_response(self, data: Dict[str, Any]):
        """Handle query response from server"""
        query_id = data.get("query_id")
        response = data.get("response")
        status = data.get("status")
        
        logger.info(f"Query Response (ID: {query_id})")
        logger.info(f"Status: {status}")
        logger.info(f"Response: {response}")
        
        print(f"\n🤖 Agent Response:")
        print(f"   Query ID: {query_id[:8]}..." if query_id else "   Query ID: Unknown")
        print(f"   Status: {status}")
        print(f"   Response: {response}")
        print()
    
    async def _handle_status_response(self, data: Dict[str, Any]):
        """Handle status response from server"""
        active_connections = data.get('active_connections', 'Unknown')
        user_id = data.get('user_id', 'Unknown')
        server_uptime = data.get('server_uptime', 'Unknown')
        
        logger.info("Server Status received:")
        logger.info(f"  Active Connections: {active_connections}")
        logger.info(f"  Your User ID: {user_id}")
        logger.info(f"  Server Uptime: {server_uptime}")
        
        print(f"\n📊 Server Status:")
        print(f"   🔗 Active Connections: {active_connections}")
        print(f"   🆔 Your User ID: {user_id}")
        print(f"   ⏱️  Server Uptime: {server_uptime}")
        print()
    
    async def _handle_text_response(self, data: Dict[str, Any]):
        """Handle text response from server"""
        response = data.get("response")
        original = data.get("original_message")
        
        logger.info(f"Text Response: {response}")
        print(f"\n💬 Server Response:")
        print(f"   {response}")
        print()
    
    async def _handle_error_response(self, data: Dict[str, Any]):
        """Handle error response from server"""
        error_message = data.get("message")
        error_type = data.get("error_type", "Unknown")
        
        logger.error(f"Server Error: {error_message}")
        print(f"\n❌ Server Error:")
        print(f"   Type: {error_type}")
        print(f"   Message: {error_message}")
        print()
    
    async def run_interactive(self):
        """Run interactive client session"""
        if not await self.connect():
            print("❌ Failed to connect to server")
            return
        
        print(f"\n✅ Connected successfully!")
        print(f"🆔 Your User ID: {self.user_id}")
        print(f"🌐 WebSocket URL: {self.websocket_url}")
        if self.api_url:
            print(f"🔗 API URL: {self.api_url}")
        
        print("\nType your message and press Enter. Available commands:")
        print("  📝 Type any text to send a message")
        print("  🤖 'query <your question>' - Send a query to the agent system")
        print("  📊 'status' - Get server status")
        print("  🚪 'exit' - Quit the client")
        print("-" * 60)
        
        try:
            while self.is_running:
                try:
                    # Get user input
                    user_input = input("> ").strip()
                    
                    if user_input.lower() == 'exit':
                        break
                    
                    if not user_input:
                        continue
                    
                    # Handle special commands
                    if user_input.lower() == 'status':
                        await self.get_status()
                    elif user_input.lower().startswith('query '):
                        query = user_input[6:].strip()
                        if query:
                            await self.send_query(query)
                        else:
                            print("❓ Please provide a query after 'query '. Example: query What is the weather?")
                    else:
                        # Send as regular text
                        await self.send_text(user_input)
                    
                    # Small delay to allow responses to be processed
                    await asyncio.sleep(0.1)
                    
                except KeyboardInterrupt:
                    print("\n🛑 Received interrupt signal...")
                    break
                except EOFError:
                    print("\n📄 End of input...")
                    break
                except Exception as e:
                    logger.error(f"Error in interactive loop: {e}", exc_info=True)
                    print(f"❌ Error: {e}")
                    
        finally:
            await self.disconnect()
            print("👋 Goodbye!")


async def main():
    """Main entry point for direct execution"""
    websocket_url = "ws://127.0.0.1:5000/ws"
    
    print("🚀 Starting Multi-Agent System Client...")
    print(f"🔗 Connecting to: {websocket_url}")
    print()
    
    client = AgentClient(websocket_url=websocket_url)
    
    try:
        await client.run_interactive()
    except Exception as e:
        logger.error(f"Client error: {e}", exc_info=True)
        print(f"❌ Client error: {e}")


if __name__ == "__main__":
    asyncio.run(main())