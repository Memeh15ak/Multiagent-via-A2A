# scripts/client_demo.py

import asyncio
import sys
import os
from loguru import logger

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logging
from client.agent_client import AgentClient


async def main():
    """Main demo function"""
    # Setup configuration
    api_url = "http://127.0.0.1:5000/api/v1"
    websocket_url = "ws://127.0.0.1:5000/ws"
    
    print("🚀 Multi-Agent System Client Demo")
    print(f"API URL: {api_url}")
    print(f"WebSocket URL: {websocket_url}")
    print()
    
    # Create client with only websocket_url (updated to match new API)
    client = AgentClient(websocket_url)
    
    try:
        # Connect to the system
        logger.info("Connecting to Multi-Agent System...")
        connected = await client.connect()
        
        if not connected:
            logger.error("Failed to connect to the Multi-Agent System")
            return
        
        logger.info("Successfully connected to Multi-Agent System")
        
        # Run interactive demo
        await demo_interactions(client)
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        await client.disconnect()


async def demo_interactions(client: AgentClient):
    """Run demo interactions with the agent system"""
    print("\n" + "="*60)
    print("🎯 DEMO: Multi-Agent System Interactions")
    print("="*60)
    
    # Demo 1: Get server status
    print("\n📊 Demo 1: Getting server status...")
    await client.get_status()
    await asyncio.sleep(2)
    
    # Demo 2: Send a simple query
    print("\n🤖 Demo 2: Sending a query to the agent system...")
    response = await client.send_query("Who won yesterday's IPL match?")
    if response:
        print(f"Query sent: {response}")
    await asyncio.sleep(3)
    
    # Demo 3: Send another query
    print("\n🤖 Demo 3: Sending another query...")
    response = await client.send_query("Who was our first prime minister?")
    if response:
        print(f"Query sent: {response}")
    await asyncio.sleep(3)
    
    
    print("\n🤖 Demo 3: Sending another query...")
    response = await client.send_query("Who won yesterdays ipl match?")
    if response:
        print(f"Query sent: {response}")
    await asyncio.sleep(3)
    
    
    # Demo 4: Send plain text message
    print("\n💬 Demo 4: Sending plain text message...")
    await client.send_text("Hello, this is a test message!")
    await asyncio.sleep(2)
    
    # Demo 5: Get status again
    print("\n📊 Demo 5: Getting final server status...")
    await client.get_status()
    await asyncio.sleep(2)
    
    # Interactive mode option
    print("\n" + "="*60)
    print("🎮 Would you like to enter interactive mode?")
    print("   In interactive mode, you can chat directly with the system.")
    print("   Type 'y' for yes, any other key to exit.")
    
    try:
        choice = input("Enter interactive mode? (y/N): ").lower().strip()
        if choice == 'y':
            print("\n🚀 Entering interactive mode...")
            print("Special commands:")
            print("  - 'status': Get server status")
            print("  - 'query <your question>': Send a query to agents")
            print("  - 'exit': Quit interactive mode")
            print("-" * 40)
            
            await interactive_mode(client)
        else:
            print("👋 Demo completed!")
            
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Demo completed!")


async def interactive_mode(client: AgentClient):
    """Interactive chat mode"""
    while True:
        try:
            user_input = input("\n> ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == 'exit':
                print("Exiting interactive mode...")
                break
            elif user_input.lower() == 'status':
                await client.get_status()
            elif user_input.lower().startswith('query '):
                query = user_input[6:].strip()
                if query:
                    await client.send_query(query)
                else:
                    print("Please provide a query after 'query '")
            else:
                await client.send_text(user_input)
            
            # Small delay to allow server response
            await asyncio.sleep(0.5)
            
        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive mode...")
            break
        except Exception as e:
            logger.error(f"Error in interactive mode: {e}")
            print(f"❌ Error: {e}")


async def demo_error_handling():
    """Demo error handling scenarios"""
    print("\n🔧 Testing error handling...")
    
    # Test connection to non-existent server
    bad_client = AgentClient("ws://127.0.0.1:9999/ws")
    
    print("Testing connection to non-existent server...")
    connected = await bad_client.connect()
    
    if not connected:
        print("✅ Error handling works - failed to connect to bad server")
    else:
        print("❌ Unexpected: connected to non-existent server")
        await bad_client.disconnect()


if __name__ == "__main__":
    # Setup logging
    setup_logging()
    
    try:
        # Run the main demo
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo interrupted. Goodbye!")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"❌ Fatal error: {e}")
        sys.exit(1)