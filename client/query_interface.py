# multi_agent_system/client/query_interface.py

import asyncio
import sys
from loguru import logger

from client.agent_client import AgentClient
from config.settings import settings

# Add a response queue to handle responses properly
class QueryInterface:
    def __init__(self, api_url: str, websocket_url: str):
        self.api_url = api_url
        self.websocket_url = websocket_url
        self.client = AgentClient(api_url, websocket_url)
        self._response_queue = asyncio.Queue()
        self.is_running = False
        
    async def setup_response_handling(self):
        """Setup response handling for the client"""
        # Add custom message handlers
        self.client.connection_manager.add_message_handler("query_response", self._handle_query_response)
        self.client.connection_manager.add_message_handler("agent_response", self._handle_agent_response)
        self.client.connection_manager.add_message_handler("orchestrator_response", self._handle_orchestrator_response)
        
    async def _handle_query_response(self, data):
        """Handle query responses"""
        await self._response_queue.put(data)
        
    async def _handle_agent_response(self, data):
        """Handle agent responses"""
        await self._response_queue.put(data)
        
    async def _handle_orchestrator_response(self, data):
        """Handle orchestrator responses"""
        await self._response_queue.put(data)
        
    async def connect(self, timeout=30):
        """Connect to the multi-agent system"""
        await self.setup_response_handling()
        return await self.client.connect()
        
    async def disconnect(self):
        """Disconnect from the system"""
        self.is_running = False
        await self.client.disconnect()
        
    async def send_query(self, query: str):
        """Send a query to the system"""
        return await self.client.send_query(query)
        
    @property
    def is_connected(self):
        """Check if connected"""
        return self.client.connection_manager.is_connected
        
    async def get_response(self):
        """Get a response from the queue"""
        try:
            return await asyncio.wait_for(self._response_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None

async def main():
    api_url = f"http://{settings.AGENT_SERVER_HOST}:{settings.AGENT_SERVER_PORT}{settings.API_V1_STR}"
    websocket_url = f"ws://{settings.AGENT_SERVER_HOST}:{settings.WEBSOCKET_PORT}/ws"
    
    logger.remove()  # Remove default logger
    logger.add(sys.stderr, level="INFO")  # Keep info and above for client console

    print("🔄 Connecting to Multi-Agent System...")
    print(f"API URL: {api_url}")
    print(f"WebSocket URL: {websocket_url}")
    
    interface = QueryInterface(api_url, websocket_url)
    
    # Try to connect with timeout
    try:
        connected = await interface.connect(timeout=30)
        if not connected:
            print("❌ Failed to connect to the Multi-Agent System.")
            print("Please ensure the server is running and accessible.")
            print("\n🔧 Troubleshooting tips:")
            print("1. Check if the server is running")
            print("2. Verify the server host and port settings")
            print("3. Check if the WebSocket endpoint is correct")
            print("4. Look at server logs for connection errors")
            return
            
        print("✅ Connected successfully!")
        print("Type your query and press Enter. Type 'exit' to quit.")
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        logger.error(f"Connection error: {e}", exc_info=True)
        return

    interface.is_running = True

    # Start a background task to receive and print responses
    async def response_printer():
        while interface.is_running:
            try:
                message = await interface.get_response()
                if message is None:
                    continue
                    
                # Filter out connection messages
                if message.get("type") == "connection_established":
                    continue
                    
                sender = message.get("sender", "System")
                content = message.get("content", message.get("response", ""))
                agent_used = message.get("agent_used", "N/A")
                is_final = message.get("is_final", True)
                query_id = message.get("query_id", "")

                # Format the response
                prefix = f"[{sender}"
                if sender == "orchestrator" and agent_used != "N/A":
                    prefix += f" via {agent_used}"
                prefix += "]"
                
                print(f"\n{prefix}: {content}")
                
                if is_final and sender == "orchestrator":
                    print("-" * 50)
                    print("Enter your next query:")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in response printer: {e}", exc_info=True)

    response_task = asyncio.create_task(response_printer())

    try:
        while interface.is_running:
            try:
                # Use asyncio.to_thread for blocking input in newer Python versions
                # For older versions, you might need a different approach
                if hasattr(asyncio, 'to_thread'):
                    query = await asyncio.to_thread(input, "> ")
                else:
                    # Fallback for older Python versions
                    query = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
                    
                if query.lower() in ['exit', 'quit', 'q']:
                    break
                    
                if query.strip() == "":
                    continue

                # Check if still connected before sending
                if not interface.is_connected:
                    print("⚠️  Connection lost. Attempting to reconnect...")
                    connected = await interface.connect()
                    if not connected:
                        print("❌ Failed to reconnect. Please restart the client.")
                        break

                print(f"📤 Sending query...")
                result = await interface.send_query(query)
                
                if result:
                    print(f"✅ Query sent successfully.")
                else:
                    print("❌ Failed to send query. Please try again.")

            except KeyboardInterrupt:
                print("\n👋 Exiting client...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                logger.error(f"Error in main loop: {e}", exc_info=True)

    except KeyboardInterrupt:
        print("\n👋 Exiting client...")
    finally:
        print("🔄 Cleaning up...")
        interface.is_running = False
        if response_task:
            response_task.cancel()
            try:
                await response_task
            except asyncio.CancelledError:
                pass
        await interface.disconnect()
        print("✅ Client disconnected successfully.")

if __name__ == "__main__":
    asyncio.run(main())