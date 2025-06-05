# agents/weather_agent/weather_agent.py - FIXED version with proper port separation
from python_a2a import A2AServer, skill, agent, run_server, TaskStatus, TaskState
from flask import Flask, jsonify, request
from loguru import logger
import asyncio
import json
import re
from typing import Dict, Any, Optional
import threading
import time
import socket
import requests

from agents.weather_agent.weather_client import WeatherClient
from config.settings import settings
from protocols.communication import comm_manager


def find_free_port(start_port: int = 5211) -> int:
    """Find a free port starting from the given port."""
    port = start_port
    while port < start_port + 100:  # Try up to 100 ports
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            port += 1
    raise RuntimeError(f"Could not find free port starting from {start_port}")


@agent(
    name="Weather Agent",
    description="Provides current weather conditions and forecasts for any location worldwide",
    version="1.0.0"
)
class WeatherAgent(A2AServer):
    
    def __init__(self):
        """Initialize the weather agent with API client."""
        super().__init__()
        self.weather_client = WeatherClient(
            settings.WEATHER_API_KEY, 
            settings.WEATHER_API_BASE_URL, 
            comm_manager
        )
        self.flask_app = None
        self.flask_port = None
        self.a2a_port = None
        logger.info("WeatherAgent initialized with decorator-based A2A protocol.")
    
    def create_flask_app(self):
        """Create Flask app for A2A discovery with correct endpoint structure."""
        app = Flask(__name__)
        
        # Disable template auto-reloading and set JSON as default
        app.config['TEMPLATES_AUTO_RELOAD'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Suppress Flask development server warning
        app.config['ENV'] = 'production'
        
        # Get agent card data
        agent_card = self.get_agent_card()
        
        @app.route('/', methods=['GET'])
        def index():
            """Root endpoint returns agent card."""
            response = jsonify(agent_card)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/.well-known/agent.json', methods=['GET'])
        def well_known_agent():
            """Standard A2A discovery endpoint - this is the key fix!"""
            response = jsonify(agent_card)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/a2a', methods=['GET'])
        def a2a_info_endpoint():
            """A2A info endpoint (discovery only - actual A2A server runs separately)."""
            a2a_info = {
                "agent": agent_card["name"],
                "a2a_server_url": f"http://127.0.0.1:{self.a2a_port}/a2a",
                "status": "discovery_service",
                "message": "This is the discovery service. A2A task processing happens at the a2a_server_url."
            }
            response = jsonify(a2a_info)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/agent-card', methods=['GET'])
        def agent_card_endpoint():
            """Agent card endpoint."""
            response = jsonify(agent_card)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/info', methods=['GET'])
        def info():
            """Info endpoint."""
            response = jsonify(agent_card)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint."""
            health_data = {
                "status": "healthy",
                "agent": "Weather Agent",
                "version": "1.0.0",
                "timestamp": time.time(),
                "services": {
                    "flask_discovery": {
                        "port": self.flask_port,
                        "status": "running",
                        "endpoints": ["/.well-known/agent.json", "/health", "/info"]
                    },
                    "a2a_server": {
                        "port": self.a2a_port,
                        "status": "running",
                        "endpoint": f"http://127.0.0.1:{self.a2a_port}/a2a"
                    }
                }
            }
            response = jsonify(health_data)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/test', methods=['GET'])
        def test_endpoint():
            """Test endpoint for diagnostics."""
            test_data = {
                "message": "Weather Agent Discovery Service is running",
                "agent": agent_card,
                "test_time": time.time(),
                "discovery_port": self.flask_port,
                "a2a_port": self.a2a_port
            }
            response = jsonify(test_data)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        # Error handlers to ensure JSON responses
        @app.errorhandler(404)
        def not_found(error):
            error_data = {
                "error": "Not Found",
                "message": "The requested endpoint was not found",
                "available_endpoints": [
                    "/", "/.well-known/agent.json", "/a2a", 
                    "/agent-card", "/info", "/health", "/test"
                ]
            }
            response = jsonify(error_data)
            response.headers['Content-Type'] = 'application/json'
            return response, 404
        
        @app.errorhandler(500)
        def internal_error(error):
            error_data = {
                "error": "Internal Server Error",
                "message": "An internal error occurred"
            }
            response = jsonify(error_data)
            response.headers['Content-Type'] = 'application/json'
            return response, 500
        
        @app.errorhandler(Exception)
        def handle_exception(e):
            """Handle all other exceptions with JSON response."""
            logger.error(f"Flask error: {e}", exc_info=True)
            error_data = {
                "error": "Server Error",
                "message": str(e)
            }
            response = jsonify(error_data)
            response.headers['Content-Type'] = 'application/json'
            return response, 500
        
        # CORS and Content-Type headers
        @app.after_request
        def after_request(response):
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            # Ensure Content-Type is application/json for all responses
            if not response.headers.get('Content-Type'):
                response.headers['Content-Type'] = 'application/json'
            return response
        
        return app
    
    def get_agent_card(self):
        """Return the agent card for discovery."""
        try:
            agent_config = settings.load_agent_config("weather_agent")
        except Exception as e:
            logger.warning(f"Could not load agent config: {e}, using defaults.")
            agent_config = None
            
        # CRITICAL FIX: Separate URLs for discovery and A2A communication
        flask_url = f"http://127.0.0.1:{self.flask_port}" if self.flask_port else "http://127.0.0.1:5211"
        a2a_url = f"http://127.0.0.1:{self.a2a_port}" if self.a2a_port else "http://127.0.0.1:5212"
        
        return {
            "id": "weather_agent_001",
            "name": "Weather Agent",
            "description": "Provides current weather conditions and forecasts for any location worldwide",
            "url": flask_url,  # Discovery service URL
            "a2a_endpoint": f"{a2a_url}/a2a",  # A2A server URL (separate port!)
            "version": "1.0.0",
            "type": "agent",
            "protocol": "a2a",
            "capabilities": {
                "streaming": False,
                "pushNotifications": False
            },
            "endpoints": {
                "discovery": f"{flask_url}/.well-known/agent.json",
                "a2a": f"{a2a_url}/a2a",
                "task": f"{a2a_url}/task", 
                "status": f"{a2a_url}/status",
                "health": f"{flask_url}/health",
                "test": f"{flask_url}/test"
            },
            "skills": [
                {
                    "id":"get_current_weather",
                    "name": "Get Current Weather",
                    "description": "Get current weather conditions for any location",
                    "tags": ["weather", "current", "conditions", "temperature"],
                    "parameters": {
                        "location": {
                            "type": "string",
                            "description": "The location to get weather for",
                            "required": True
                        }
                    }
                },
                {
                    "id": "get_weather_forcast",
                    "name": "Get Weather Forecast", 
                    "description": "Get weather forecast for a location (up to 10 days)",
                    "tags": ["weather", "forecast", "prediction", "future"],
                    "parameters": {
                        "location": {
                            "type": "string", 
                            "description": "The location to get forecast for",
                            "required": True
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days for forecast (1-10)",
                            "required": False,
                            "default": 3
                        }
                    }
                }
            ]
        }
    
    @skill(
        name="Get Current Weather",
        description="Get current weather conditions for any location",
        tags=["weather", "current", "conditions", "temperature"]
    )
    async def get_current_weather(self, location: str) -> str:
        """Get current weather for a location."""
        try:
            logger.info(f"Getting current weather for: {location}")
            weather_data = await self.weather_client.get_current_weather(location)
            return self._format_weather_response(location, weather_data)
        except Exception as e:
            logger.error(f"Error getting current weather for {location}: {e}")
            return f"Sorry, I couldn't get current weather information for {location}. Please try again."
    
    @skill(
        name="Get Weather Forecast",
        description="Get weather forecast for a location (up to 10 days)",
        tags=["weather", "forecast", "prediction", "future"]
    )
    async def get_weather_forecast(self, location: str, days: int = 3) -> str:
        """Get weather forecast for a location."""
        try:
            logger.info(f"Getting {days}-day forecast for: {location}")
            forecast_data = await self.weather_client.get_weather_forecast(location, days)
            return self._format_forecast_response(location, forecast_data, days)
        except Exception as e:
            logger.error(f"Error getting forecast for {location}: {e}")
            return f"Sorry, I couldn't get forecast information for {location}. Please try again."

    def handle_task(self, task):
        """Handle incoming A2A tasks with natural language processing."""
        try:
            # Extract message content
            message_data = task.message or {}
            content = message_data.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else ""
            
            logger.info(f"WeatherAgent received task with text: {text}")
            
            if not text:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent", 
                        "content": {
                            "type": "text", 
                            "text": "Please ask me about weather! Examples: 'What's the weather in New York?' or 'Get 5-day forecast for London'"
                        }
                    }
                )
                return task
            
            # Parse the request
            location = self._extract_location_from_text(text.lower())
            if not location:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent",
                        "content": {
                            "type": "text",
                            "text": "Please specify a location. Examples: 'weather in Paris', 'forecast for Tokyo', 'current conditions in London'"
                        }
                    }
                )
                return task
            
            # Determine if it's a forecast or current weather request
            is_forecast = any(word in text.lower() for word in ["forecast", "tomorrow", "next", "future", "upcoming", "week", "days"])
            
            if is_forecast:
                days = self._extract_days_from_text(text.lower())
                weather_response = asyncio.run(self.get_weather_forecast(location, days))
            else:
                weather_response = asyncio.run(self.get_current_weather(location))
            
            # Create successful response
            task.artifacts = [{
                "parts": [{"type": "text", "text": weather_response}]
            }]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
        except Exception as e:
            logger.error(f"Error handling weather task: {e}", exc_info=True)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={
                    "role": "agent",
                    "content": {
                        "type": "text",
                        "text": f"Sorry, I encountered an error processing your weather request: {str(e)}"
                    }
                }
            )
        
        return task

    def _extract_location_from_text(self, text: str) -> Optional[str]:
        """Extract location from natural language text."""
        # Common patterns for location extraction
        patterns = [
            r'(?:weather|forecast|conditions)\s+(?:in|for|at)\s+([a-zA-Z\s,]+?)(?:\s|$|\?|!|\.|,)',
            r'(?:in|for|at)\s+([a-zA-Z\s,]+?)(?:\s|$|\?|!|\.|weather|forecast)',
            r'([A-Z][a-zA-Z\s,]+?)(?:\s+weather|\s+forecast|\?|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip().rstrip(',')
                # Clean up common words that might be captured
                location = re.sub(r'\b(weather|forecast|conditions|current|today|tomorrow)\b', '', location, flags=re.IGNORECASE).strip()
                if location and len(location) > 1:
                    return location
        
        # Fallback: look for capitalized words
        words = text.split()
        capitalized_words = []
        for word in words:
            clean_word = re.sub(r'[^\w\s]', '', word)
            if clean_word and clean_word[0].isupper() and clean_word.isalpha():
                capitalized_words.append(clean_word)
        
        if capitalized_words:
            return " ".join(capitalized_words[:2])  # Max 2 words for location
        
        return None

    def _extract_days_from_text(self, text: str) -> int:
        """Extract number of days from text query."""
        # Look for specific day numbers
        day_patterns = [
            (r'(\d+)\s*(?:day|days)', lambda m: int(m.group(1))),
            (r'(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:day|days)', 
             lambda m: {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 
                       'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}.get(m.group(1), 3)),
            (r'week', lambda m: 7),
            (r'tomorrow', lambda m: 1),
        ]
        
        for pattern, converter in day_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    days = converter(match)
                    return min(max(days, 1), 10)  # Clamp between 1-10 days
                except (ValueError, KeyError):
                    continue
        
        return 3  # Default

    def _format_weather_response(self, location: str, data: Dict[str, Any]) -> str:
        """Format current weather data into a readable response."""
        if not data:
            return f"Could not retrieve current weather for {location}."
        
        current = data.get("current", {})
        location_info = data.get("location", {})
        display_location = location_info.get("name", location)
        country = location_info.get("country", "")
        if country:
            display_location = f"{display_location}, {country}"
        
        temp_c = current.get("temp_c")
        condition = current.get("condition", {}).get("text")
        wind_kph = current.get("wind_kph")
        humidity = current.get("humidity")
        feels_like = current.get("feelslike_c")

        if temp_c is not None and condition:
            response = f"🌤️ Current weather in {display_location}:\n\n"
            response += f"• Condition: {condition}\n"
            response += f"• Temperature: {temp_c}°C"
            if feels_like and abs(feels_like - temp_c) > 1:
                response += f" (feels like {feels_like}°C)"
            response += f"\n• Wind: {wind_kph} km/h\n"
            response += f"• Humidity: {humidity}%"
            return response
        
        return f"Could not get detailed weather information for {location}. Please try again."

    def _format_forecast_response(self, location: str, data: Dict[str, Any], days: int) -> str:
        """Format forecast data into a readable response."""
        if not data or "forecast" not in data or "forecastday" not in data["forecast"]:
            return f"Could not retrieve weather forecast for {location}."

        location_info = data.get("location", {})
        display_location = location_info.get("name", location)
        country = location_info.get("country", "")
        if country:
            display_location = f"{display_location}, {country}"

        forecast_days = data["forecast"]["forecastday"][:days]
        response_lines = [f"📅 Weather forecast for {display_location} ({len(forecast_days)} days):\n"]

        for i, day_data in enumerate(forecast_days):
            date = day_data["date"]
            day_info = day_data["day"]
            max_temp_c = day_info.get("maxtemp_c")
            min_temp_c = day_info.get("mintemp_c")
            condition = day_info.get("condition", {}).get("text")
            chance_of_rain = day_info.get("daily_chance_of_rain", 0)
            
            day_label = "Today" if i == 0 else "Tomorrow" if i == 1 else date
            response_lines.append(f"🗓️ **{day_label}** ({date}):")
            response_lines.append(f"   • {condition}")
            response_lines.append(f"   • High: {max_temp_c}°C, Low: {min_temp_c}°C")
            if chance_of_rain > 0:
                response_lines.append(f"   • Chance of rain: {chance_of_rain}%")
            response_lines.append("")
        
        return "\n".join(response_lines)


async def start_weather_agent():
    """Start the weather agent with proper port separation for discovery and A2A services."""
    try:
        agent_config = settings.load_agent_config("weather_agent")
        if not agent_config:
            logger.warning("Weather agent config not found, using defaults.")
    except Exception as e:
        logger.warning(f"Could not load agent config: {e}, using defaults.")

    # CRITICAL FIX: Use separate ports for Flask discovery and A2A server
    try:
        base_port = settings.get_agent_port("weather_agent") or 5211
    except Exception as e:
        logger.warning(f"Could not get agent port: {e}, using default 5211")
        base_port = 5211
    
    # Find available ports - Flask discovery first, then A2A server
    flask_port = find_free_port(base_port)
    a2a_port = find_free_port(flask_port + 1)  # Start looking after flask_port
    
    agent = WeatherAgent()
    agent.flask_port = flask_port
    agent.a2a_port = a2a_port
    
    logger.info(f"🌤️ Weather Agent configuration:")
    logger.info(f"  📍 Flask Discovery Port: {flask_port}")
    logger.info(f"  🤖 A2A Server Port: {a2a_port}")
    logger.info(f"  🔍 Discovery URL: http://127.0.0.1:{flask_port}/.well-known/agent.json")
    logger.info(f"  💬 A2A URL: http://127.0.0.1:{a2a_port}/a2a")
    
    # Create and start Flask app for discovery
    flask_app = agent.create_flask_app()
    
    def run_flask():
        try:
            logger.info(f"🚀 Starting Flask discovery server on port {flask_port}")
            flask_app.run(
                host='127.0.0.1', 
                port=flask_port, 
                debug=False, 
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            logger.error(f"❌ Flask server error: {e}")
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Give Flask time to start and verify it's accessible
    await asyncio.sleep(2)
    
    try:
        # Test the discovery endpoint
        discovery_url = f"http://127.0.0.1:{flask_port}/.well-known/agent.json"
        response = requests.get(discovery_url, timeout=5)
        if response.status_code == 200:
            logger.info(f"✅ Flask discovery server is running and accessible")
            logger.info(f"✅ Agent card discoverable at: {discovery_url}")
        else:
            logger.warning(f"⚠️ Discovery endpoint returned status {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Could not verify Flask discovery server: {e}")
        logger.info("🔄 Continuing anyway - Flask might still be starting up...")
    
    # Start A2A server on separate port
    try:
        logger.info(f"🚀 Starting A2A server on port {a2a_port}...")
        logger.info("=" * 50)
        await run_server(agent, host="127.0.0.1", port=a2a_port)
    except Exception as e:
        logger.error(f"❌ Error starting A2A server: {e}")


def main():
    """Main entry point for running the weather agent."""
    logger.info("🌤️ Weather Agent Server Starting...")
    logger.info("=" * 50)
    
    try:
        asyncio.run(start_weather_agent())
    except KeyboardInterrupt:
        logger.info("🛑 Weather Agent Server stopped by user")
    except Exception as e:
        logger.error(f"❌ Weather Agent Server error: {e}", exc_info=True)


# Run the server
if __name__ == "__main__":
    main()