# multi_agent_system/tests/test_integration.py

import pytest
import asyncio
import httpx
import websockets
import json
from loguru import logger
from multiprocessing import Process

# Import server and agent startup functions
from server.agent_server import app as main_app # FastAPI app
from agents.weather_agent.weather_agent import start_weather_agent
from agents.web_search_agent.search_agent import start_web_search_agent
from agents.news_agent.news_agent import start_news_agent
from config.settings import settings

# Configure settings for testing
settings.AGENT_SERVER_PORT = 8005
settings.WEBSOCKET_PORT = 8006
settings.A2A_AGENT_BASE_URL = "http://127.0.0.1" # For A2A agent servers
settings.PERPLEXITY_API_KEY = "dummy_perplexity_key" # Mock this for tests

# Ports for individual A2A agents (must match agent_config.yaml)
WEATHER_AGENT_PORT = 5001
WEB_SEARCH_AGENT_PORT = 5002
NEWS_AGENT_PORT = 5003

@pytest.fixture(scope="module")
def setup_server_and_agents():
    """
    Spins up the FastAPI server and the individual A2A agents in separate processes.
    """
    logger.info("Setting up integration test environment...")

    server_process = Process(target=run_fastapi_server)
    weather_agent_process = Process(target=run_a2a_agent, args=(start_weather_agent,))
    web_search_agent_process = Process(target=run_a2a_agent, args=(start_web_search_agent,))
    news_agent_process = Process(target=run_a2a_agent, args=(start_news_agent,))

    server_process.start()
    weather_agent_process.start()
    web_search_agent_process.start()
    news_agent_process.start()

    # Give services time to start up
    asyncio.run(asyncio.sleep(5))
    logger.info("All services started.")

    yield # Tests run here

    logger.info("Tearing down integration test environment...")
    server_process.terminate()
    weather_agent_process.terminate()
    web_search_agent_process.terminate()
    news_agent_process.terminate()

    server_process.join(timeout=5)
    weather_agent_process.join(timeout=5)
    web_search_agent_process.join(timeout=5)
    news_agent_process.join(timeout=5)

    logger.info("All services torn down.")

def run_fastapi_server():
    """Helper to run the FastAPI server in a separate process."""
    import uvicorn
    # Suppress uvicorn logs for cleaner test output, if desired
    # uvicorn.run(main_app, host=settings.AGENT_SERVER_HOST, port=settings.AGENT_SERVER_PORT, log_level="error")
    uvicorn.run(main_app, host=settings.AGENT_SERVER_HOST, port=settings.AGENT_SERVER_PORT)

def run_a2a_agent(start_func):
    """Helper to run an A2A agent in a separate process."""
    # Ensure a clean event loop for each process
    asyncio.run(start_func())

@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_server_and_agents")
async def test_end_to_end_weather_query():
    logger.info("Running end-to-end weather query test.")
    api_url = f"http://{settings.AGENT_SERVER_HOST}:{settings.AGENT_SERVER_PORT}{settings.API_V1_STR}"
    websocket_url = f"ws://{settings.AGENT_SERVER_HOST}:{settings.WEBSOCKET_PORT}/ws"
    test_user_id = "test_user_123"
    test_query = "What is the weather like in London?"

    async with websockets.connect(websocket_url) as ws:
        # 1. Receive connection established message from WebSocket
        conn_msg = json.loads(await ws.recv())
        assert conn_msg["type"] == "connection_established"
        client_user_id = conn_msg["user_id"] # Use the ID assigned by server

        async with httpx.AsyncClient() as client:
            # 2. Send query via HTTP API
            response = await client.post(
                f"{api_url}/query",
                json={"user_id": client_user_id, "query": test_query}
            )
            response.raise_for_status()
            api_response = response.json()
            assert api_response["status"] == "accepted"
            query_id = api_response["query_id"]
            logger.info(f"API acknowledged query: {query_id}")

            # 3. Receive responses via WebSocket
            received_final_response = False
            while not received_final_response:
                ws_message_raw = await ws.recv()
                ws_message = json.loads(ws_message_raw)
                logger.info(f"Received WS message: {ws_message}")

                if ws_message.get("query_id") == query_id:
                    assert ws_message["sender"] == "orchestrator"
                    assert "weather" in ws_message["content"].lower() # Expect weather data
                    assert ws_message["is_final"] is True
                    received_final_response = True
                    break # Exit loop once final response is received
                else:
                    logger.debug(f"Skipping WS message for different query_id or no query_id: {ws_message}")

            assert received_final_response, "Did not receive final response for the query via WebSocket."
            logger.info("Weather query test successful!")

# Add more end-to-end tests for other agents and scenarios.