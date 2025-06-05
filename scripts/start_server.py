# multi_agent_system/scripts/start_server.py

import uvicorn
import asyncio
import sys
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

# Add the project root to the sys.path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server.agent_server import app
from config.settings import settings
from utils.logger import setup_logging, logger

# Import the core components
from core.message_broker import message_broker
from core.query_handler import query_handler

def check_agent_availability():
    """Check if all A2A agents are available and running."""
    agents_to_check = [
        ("Weather Agent", "weather_agent"),
        ("Web Search Agent", "web_search_agent"), 
        ("News Agent", "news_agent")
    ]
    
    available_agents = []
    unavailable_agents = []
    
    for agent_name, agent_id in agents_to_check:
        try:
            config = settings.load_agent_config(agent_id)
            if config:
                port = settings.get_agent_port(agent_id)
                endpoint = config.get("a2a_endpoint", f"http://127.0.0.1:{port}")
                available_agents.append((agent_name, endpoint))
                logger.info(f"✅ {agent_name} configured at {endpoint}")
            else:
                unavailable_agents.append(agent_name)
                logger.warning(f"⚠️ {agent_name} configuration not found")
        except Exception as e:
            unavailable_agents.append(agent_name)
            logger.warning(f"⚠️ {agent_name} configuration error: {e}")
    
    return available_agents, unavailable_agents

def display_server_info():
    """Display server startup information."""
    logger.info("=" * 70)
    logger.info("🚀 MULTI-AGENT SYSTEM SERVER STARTUP")
    logger.info("=" * 70)
    logger.info(f"🌐 FastAPI Server: http://{settings.AGENT_SERVER_HOST}:{settings.AGENT_SERVER_PORT}")
    logger.info(f"🔌 WebSocket Server: ws://{settings.AGENT_SERVER_HOST}:{settings.AGENT_SERVER_PORT}/ws")
    logger.info(f"📊 Environment: {settings.ENVIRONMENT}")
    logger.info(f"🔧 Debug Mode: {settings.DEBUG}")
    logger.info("")
    
    # Check and display agent availability
    available_agents, unavailable_agents = check_agent_availability()
    
    if available_agents:
        logger.info("🤖 Available A2A Agents:")
        for agent_name, endpoint in available_agents:
            logger.info(f"   • {agent_name}: {endpoint}")
    
    if unavailable_agents:
        logger.info("⚠️ Unavailable Agents:")
        for agent_name in unavailable_agents:
            logger.info(f"   • {agent_name}")
    
    logger.info("")
    logger.info("💡 API Documentation available at:")
    logger.info(f"   • Swagger UI: http://{settings.AGENT_SERVER_HOST}:{settings.AGENT_SERVER_PORT}/docs")
    logger.info(f"   • ReDoc: http://{settings.AGENT_SERVER_HOST}:{settings.AGENT_SERVER_PORT}/redoc")
    logger.info("=" * 70)

def validate_configuration():
    """Validate server configuration before startup."""
    errors = []
    warnings = []
    
    # Check required settings
    if not settings.AGENT_SERVER_HOST:
        errors.append("AGENT_SERVER_HOST is not configured")
    
    if not settings.AGENT_SERVER_PORT:
        errors.append("AGENT_SERVER_PORT is not configured")
    
    # Check for agent configurations
    agent_configs = ["weather_agent", "web_search_agent", "news_agent"]
    missing_configs = []
    
    for agent_id in agent_configs:
        try:
            if not settings.load_agent_config(agent_id):
                missing_configs.append(agent_id)
        except Exception as e:
            missing_configs.append(agent_id)
    
    if missing_configs:
        warnings.append(f"Missing agent configurations: {', '.join(missing_configs)}")
    
    # Report validation results
    if errors:
        logger.error("❌ Configuration validation failed:")
        for error in errors:
            logger.error(f"   • {error}")
        return False
    
    if warnings:
        logger.warning("⚠️ Configuration warnings:")
        for warning in warnings:
            logger.warning(f"   • {warning}")
    
    logger.info("✅ Configuration validation passed")
    return True

async def initialize_core_components():
    """Initialize the core components (message broker and query handler)."""
    try:
        logger.info("🔧 Initializing core components...")
        
        # Start message broker
        await message_broker.start()
        logger.info("✅ Message broker initialized successfully")
        
        # Start query handler
        await query_handler.start()
        logger.info("✅ Query handler initialized successfully")
        
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize core components: {e}")
        return False

async def wait_for_agents():
    """Wait for A2A agents to be available (optional)."""
    logger.info("⏳ Waiting for A2A agents to be ready...")
    
    # Simple retry logic to check if agents are responding
    max_retries = 30  # 30 seconds
    retry_delay = 1   # 1 second between retries
    
    for attempt in range(max_retries):
        available_agents, unavailable_agents = check_agent_availability()
        
        if len(available_agents) >= 1:  # At least one agent is available
            logger.info(f"✅ Found {len(available_agents)} available agents")
            return True
        
        if attempt < max_retries - 1:  # Don't sleep on the last attempt
            await asyncio.sleep(retry_delay)
    
    logger.warning("⚠️ Some agents may not be ready yet, but continuing with server startup")
    return True

async def startup_checks():
    """Perform startup checks and initialization."""
    logger.info("🔍 Performing startup checks...")
    
    # Validate configuration
    if not validate_configuration():
        logger.error("Server startup aborted due to configuration errors")
        return False
    
    # Initialize core components (CRITICAL - this was missing!)
    if not await initialize_core_components():
        logger.error("Server startup aborted due to core component initialization failure")
        return False
    
    # Wait for agents to be ready (optional but recommended)
    await wait_for_agents()
    
    logger.info("✅ All startup checks passed")
    return True

def configure_uvicorn():
    """Configure Uvicorn server settings."""
    config = {
        "app": app,
        "host": settings.AGENT_SERVER_HOST,
        "port": settings.AGENT_SERVER_PORT,
        "ws_max_size": 1024 * 1024 * 10,  # 10MB max WebSocket message size
        "log_level": "info",
        "access_log": True,
        "server_header": False,  # Don't expose server header
        "date_header": False,    # Don't expose date header
    }
    
    # Development-specific settings
    if settings.DEBUG:
        config.update({
            "reload": True,
            "reload_dirs": [
                os.path.join(os.path.dirname(__file__), '..', 'server'),
                os.path.join(os.path.dirname(__file__), '..', 'agents'),
                os.path.join(os.path.dirname(__file__), '..', 'core'),  # Added core directory
            ],
            "log_level": "debug"
        })
        logger.info("🔧 Development mode: Hot-reloading enabled")
    
    return config

async def main_async():
    """Async main function for startup checks."""
    setup_logging()
    
    # Perform startup checks (including core component initialization)
    if not await startup_checks():
        sys.exit(1)
    
    # Display server information
    display_server_info()
    
    # Configure and start the server
    config = configure_uvicorn()
    
    logger.info("🚀 Starting Multi-Agent System Server...")
    logger.info("📨 Message broker and query handler are active and ready to process queries")
    logger.info("Press Ctrl+C to stop the server")
    
    # Start the server
    server = uvicorn.Server(uvicorn.Config(**config))
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("🛑 Server shutdown requested")
    except Exception as e:
        logger.error(f"❌ Server error: {e}")
        raise
    finally:
        # Cleanup
        try:
            await message_broker.stop()
            logger.info("🏁 Message broker stopped")
        except Exception as e:
            logger.error(f"Error stopping message broker: {e}")
        
        logger.info("🏁 Server stopped")

def main():
    """Main entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("🛑 Shutdown signal received")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()