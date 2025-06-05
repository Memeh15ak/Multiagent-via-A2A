# multi_agent_system/scripts/start_agents.py

import asyncio
import multiprocessing
import os
import sys
import time
from loguru import logger

# Add the project root to the sys.path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.weather_agent.weather_agent import start_weather_agent
from agents.web_search_agent.search_agent import start_web_search_agent
from agents.news_agent.news_agent import start_news_agent
from utils.logger import setup_logging
from config.settings import settings

def run_agent_process(agent_start_func, agent_name):
    """Helper function to run an async agent startup function in a new event loop."""
    try:
        logger.info(f"Starting {agent_name} in process {os.getpid()}")
        asyncio.run(agent_start_func())
    except Exception as e:
        logger.error(f"Error starting {agent_name}: {e}", exc_info=True)
        raise

def check_agent_config():
    """Check if all required agent configurations are available."""
    required_agents = ["weather_agent", "web_search_agent", "news_agent"]
    missing_configs = []
    
    for agent_id in required_agents:
        agent_config = settings.load_agent_config(agent_id)
        if not agent_config:
            missing_configs.append(agent_id)
        else:
            port = settings.get_agent_port(agent_id)
            if port is None:
                logger.warning(f"Could not determine port for {agent_id}")
    
    if missing_configs:
        logger.error(f"Missing configurations for agents: {missing_configs}")
        return False
    
    return True

def display_agent_info():
    """Display information about the agents that will be started."""
    logger.info("=" * 60)
    logger.info("A2A MULTI-AGENT SYSTEM STARTUP")
    logger.info("=" * 60)
    
    agents_info = [
        ("Weather Agent", "weather_agent", "Provides weather conditions and forecasts"),
        ("Web Search Agent", "web_search_agent", "Performs web searches and content retrieval"),
        ("News Agent", "news_agent", "Fetches and provides news information")
    ]
    
    for agent_name, agent_id, description in agents_info:
        config = settings.load_agent_config(agent_id)
        if config:
            port = settings.get_agent_port(agent_id)
            endpoint = config.get("a2a_endpoint", f"http://127.0.0.1:{port}")
            logger.info(f"🤖 {agent_name}")
            logger.info(f"   Description: {description}")
            logger.info(f"   Endpoint: {endpoint}")
            logger.info(f"   Port: {port}")
            logger.info("")

def monitor_processes(processes):
    """Monitor running processes and restart if they crash."""
    while True:
        try:
            time.sleep(5)  # Check every 5 seconds
            
            for agent_name, process, start_func in processes:
                if not process.is_alive():
                    logger.warning(f"{agent_name} process has died (exit code: {process.exitcode})")
                    logger.info(f"Restarting {agent_name}...")
                    
                    # Start a new process
                    new_process = multiprocessing.Process(
                        target=run_agent_process, 
                        args=(start_func, agent_name)
                    )
                    new_process.start()
                    
                    # Update the process in the list
                    for i, (name, proc, func) in enumerate(processes):
                        if name == agent_name:
                            processes[i] = (name, new_process, func)
                            break
                    
                    logger.info(f"Restarted {agent_name} (new PID: {new_process.pid})")
                    
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error in process monitoring: {e}")

def main():
    setup_logging()
    
    # Check configurations before starting
    if not check_agent_config():
        logger.error("Agent configuration check failed. Exiting.")
        sys.exit(1)
    
    display_agent_info()
    
    logger.info("Starting all A2A agents...")

    agents_to_start = {
        "Weather Agent": start_weather_agent,
        "Web Search Agent": start_web_search_agent,
        "News Agent": start_news_agent,
    }

    processes = []
    
    # Start all agent processes
    for agent_name, start_func in agents_to_start.items():
        try:
            process = multiprocessing.Process(
                target=run_agent_process, 
                args=(start_func, agent_name)
            )
            process.start()
            processes.append((agent_name, process, start_func))
            logger.info(f"✅ Started {agent_name} (PID: {process.pid})")
            time.sleep(1)  # Give each process time to start
            
        except Exception as e:
            logger.error(f"❌ Failed to start {agent_name}: {e}")
            continue

    if not processes:
        logger.error("No agents were started successfully. Exiting.")
        sys.exit(1)

    # Verify all processes are running
    time.sleep(2)
    running_agents = []
    failed_agents = []
    
    for agent_name, process, start_func in processes:
        if process.is_alive():
            running_agents.append(agent_name)
        else:
            failed_agents.append(agent_name)
    
    if running_agents:
        logger.info("🎉 Successfully started agents:")
        for agent in running_agents:
            logger.info(f"   • {agent}")
    
    if failed_agents:
        logger.warning("⚠️ Failed to start agents:")
        for agent in failed_agents:
            logger.warning(f"   • {agent}")

    logger.info("=" * 60)
    logger.info("All configured agents are running.")
    logger.info("Press Ctrl+C to stop all agents.")
    logger.info("=" * 60)

    try:
        # Monitor processes and keep main thread alive
        monitor_processes(processes)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Shutdown signal received. Stopping all agents...")
        
    finally:
        # Graceful shutdown
        logger.info("Initiating graceful shutdown...")
        
        for agent_name, process, _ in processes:
            if process.is_alive():
                logger.info(f"Stopping {agent_name} (PID: {process.pid})...")
                process.terminate()
        
        # Wait for graceful termination
        shutdown_timeout = 10
        for agent_name, process, _ in processes:
            try:
                process.join(timeout=shutdown_timeout)
                if process.is_alive():
                    logger.warning(f"{agent_name} did not stop gracefully. Force killing...")
                    process.kill()
                    process.join(timeout=5)
                else:
                    logger.info(f"✅ {agent_name} stopped gracefully")
            except Exception as e:
                logger.error(f"Error stopping {agent_name}: {e}")
        
        logger.info("🏁 All agents have been stopped.")

if __name__ == "__main__":
    main()