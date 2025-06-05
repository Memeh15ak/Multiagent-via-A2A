# agents/web_search_agent/web_search_agent.py - FIXED version with proper JSON responses
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

from agents.web_search_agent.search_client import DuckDuckGoSearchClient
from config.settings import settings
from protocols.communication import comm_manager


def find_free_port(start_port: int = 5512) -> int:
    """Find a free port starting from the given port number."""
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find free port starting from {start_port}")


@agent(
    name="Web Search Agent",
    description="Performs web searches using DuckDuckGo and returns relevant results",
    version="1.0.0"
)
class WebSearchAgent(A2AServer):
    
    def __init__(self):
        """Initialize the web search agent with search client."""
        super().__init__()
        self.search_client = DuckDuckGoSearchClient(comm_manager)
        self.flask_app = None
        self.flask_port = None
        self.a2a_port = None
        self.flask_thread = None
        logger.info("WebSearchAgent initialized with decorator-based A2A protocol.")
    
    def create_flask_app(self):
        """Create Flask app for A2A discovery with STRICT JSON responses."""
        app = Flask(__name__)
        
        # CRITICAL: Disable all template rendering and HTML responses
        app.config['TEMPLATES_AUTO_RELOAD'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
        app.config['JSON_SORT_KEYS'] = False
        
        # Get agent card data
        agent_card = self.get_agent_card()
        
        # CRITICAL FIX: Force JSON response helper
        def force_json_response(data, status_code=200):
            """Force a JSON response with proper headers."""
            response = jsonify(data)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'no-cache'
            response.status_code = status_code
            return response
        
        @app.route('/', methods=['GET'])
        def index():
            """Root endpoint returns agent card."""
            logger.debug("Flask: Root endpoint accessed")
            return force_json_response(agent_card)
        
        @app.route('/.well-known/agent.json', methods=['GET'])
        def well_known_agent():
            """Standard A2A discovery endpoint - CRITICAL FOR DISCOVERY!"""
            logger.info("Flask: A2A discovery endpoint accessed")
            return force_json_response(agent_card)
        
        @app.route('/a2a', methods=['GET'])
        def a2a_endpoint():
            """A2A protocol endpoint for discovery."""
            logger.debug("Flask: A2A endpoint accessed")
            return force_json_response(agent_card)
        
        @app.route('/agent-card', methods=['GET'])
        def agent_card_endpoint():
            """Agent card endpoint."""
            logger.debug("Flask: Agent card endpoint accessed")
            return force_json_response(agent_card)
        
        @app.route('/info', methods=['GET'])
        def info():
            """Info endpoint."""
            logger.debug("Flask: Info endpoint accessed")
            return force_json_response(agent_card)
        
        @app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint."""
            logger.debug("Flask: Health endpoint accessed")
            health_data = {
                "status": "healthy",
                "agent": "Web Search Agent",
                "version": "1.0.0",
                "timestamp": time.time(),
                "ports": {
                    "flask": self.flask_port,
                    "a2a": self.a2a_port
                },
                "services": {
                    "flask_discovery": f"http://127.0.0.1:{self.flask_port}",
                    "a2a_server": f"http://127.0.0.1:{self.a2a_port}/a2a"
                }
            }
            return force_json_response(health_data)
        
        @app.route('/test', methods=['GET'])
        def test_endpoint():
            """Test endpoint for diagnostics."""
            logger.debug("Flask: Test endpoint accessed")
            test_data = {
                "message": "Web Search Agent Flask discovery server is running",
                "agent": agent_card,
                "test_time": time.time(),
                "discovery_working": True
            }
            return force_json_response(test_data)
        
        # CRITICAL: Error handlers must return JSON, not HTML
        @app.errorhandler(404)
        def not_found(error):
            logger.warning(f"Flask: 404 error for path: {request.path}")
            error_data = {
                "error": "Not Found",
                "message": f"The requested endpoint '{request.path}' was not found",
                "available_endpoints": [
                    "/", "/.well-known/agent.json", "/a2a", 
                    "/agent-card", "/info", "/health", "/test"
                ]
            }
            return force_json_response(error_data, 404)
        
        @app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Flask: 500 error: {error}")
            error_data = {
                "error": "Internal Server Error",
                "message": "An internal error occurred"
            }
            return force_json_response(error_data, 500)
        
        @app.errorhandler(Exception)
        def handle_exception(e):
            """Handle all other exceptions with JSON response."""
            logger.error(f"Flask error: {e}", exc_info=True)
            error_data = {
                "error": "Server Error",
                "message": str(e)
            }
            return force_json_response(error_data, 500)
        
        # CORS and headers
        @app.before_request
        def before_request():
            """Set JSON content type for all requests."""
            if request.method == 'GET':
                # Force JSON response preparation
                pass
        
        @app.after_request
        def after_request(response):
            """Ensure all responses are JSON with proper headers."""
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            
            # CRITICAL: Force JSON content type
            if not response.headers.get('Content-Type'):
                response.headers['Content-Type'] = 'application/json'
            elif 'text/html' in response.headers.get('Content-Type', ''):
                # Fix any HTML responses to JSON
                logger.warning("Detected HTML response, forcing JSON content type")
                response.headers['Content-Type'] = 'application/json'
            
            return response
        
        return app
    
    def get_agent_card(self):
        """Return the agent card for discovery."""
        try:
            agent_config = settings.load_agent_config("web_search_agent")
            base_port = self.flask_port or 5512
            
            # Use the Flask port for discovery URL
            base_url = f"http://127.0.0.1:{base_port}"
            a2a_url = f"http://127.0.0.1:{self.a2a_port}/a2a" if self.a2a_port else f"{base_url}/a2a"
            
            return {
                "id": "web_search_agent_001",
                "name": "Web Search Agent",
                "description": "Performs web searches using DuckDuckGo and returns relevant results",
                "url": base_url,
                "a2a_endpoint": a2a_url,
                "version": "1.0.0",
                "type": "agent",
                "protocol": "a2a",
                "capabilities": {
                    "streaming": False,
                    "pushNotifications": False
                },
                "endpoints": {
                    "discovery": f"{base_url}/.well-known/agent.json",
                    "a2a": a2a_url,
                    "health": f"{base_url}/health",
                    "test": f"{base_url}/test"
                },
                "skills": [
                    {
                        "id": "search_web",
                        "name": "Search Web",
                        "description": "Search the web using DuckDuckGo and return relevant results",
                        "tags": ["search", "web", "internet", "query", "results"],
                        "parameters": {
                            "query": {
                                "type": "string",
                                "description": "The search query to look for on the web",
                                "required": True
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (1-10)",
                                "required": False,
                                "default": 5
                            }
                        }
                    },
                    {
                        "id": "search_news",
                        "name": "Search News",
                        "description": "Search for recent news articles using DuckDuckGo",
                        "tags": ["search", "news", "current", "articles"],
                        "parameters": {
                            "query": {
                                "type": "string",
                                "description": "The news search query",
                                "required": True
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of news results to return (1-10)",
                                "required": False,
                                "default": 5
                            }
                        }
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error creating agent card: {e}")
            # Return a minimal agent card if config fails
            return {
                "id": "web_search_agent_001",
                "name": "Web Search Agent",
                "description": "Performs web searches using DuckDuckGo and returns relevant results",
                "url": f"http://127.0.0.1:{self.flask_port or 5512}",
                "a2a_endpoint": f"http://127.0.0.1:{self.a2a_port or 5513}",
                "version": "1.0.0",
                "type": "agent",
                "protocol": "a2a",
                "status": "error",
                "error": str(e)
            }
    
    @skill(
        name="Search Web",
        description="Search the web using DuckDuckGo and return relevant results",
        tags=["search", "web", "internet", "query", "results"]
    )
    async def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web for a query."""
        try:
            logger.info(f"Searching web for: {query}")
            search_data = await self.search_client.search_web(query)
            return self._format_search_response(query, search_data, max_results)
        except Exception as e:
            logger.error(f"Error searching web for {query}: {e}")
            return f"Sorry, I couldn't search for '{query}'. Please try again."
    
    @skill(
        name="Search News",
        description="Search for recent news articles using DuckDuckGo",
        tags=["search", "news", "current", "articles"]
    )
    async def search_news(self, query: str, max_results: int = 5) -> str:
        """Search for news articles related to a query."""
        try:
            logger.info(f"Searching news for: {query}")
            news_query = f"{query} news"
            search_data = await self.search_client.search_web(news_query)
            return self._format_news_response(query, search_data, max_results)
        except Exception as e:
            logger.error(f"Error searching news for {query}: {e}")
            return f"Sorry, I couldn't search for news about '{query}'. Please try again."

    def handle_task(self, task):
        """Handle incoming A2A tasks with natural language processing."""
        try:
            # Extract message content
            message_data = task.message or {}
            content = message_data.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else ""
            
            logger.info(f"WebSearchAgent received task with text: {text}")
            
            if not text:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent", 
                        "content": {
                            "type": "text", 
                            "text": "Please ask me to search for something! Examples: 'Search for Python tutorials' or 'Find news about AI'"
                        }
                    }
                )
                return task
            
            # Parse the request
            query = self._extract_query_from_text(text.lower())
            if not query:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent",
                        "content": {
                            "type": "text",
                            "text": "Please specify what you'd like me to search for. Examples: 'search for AI news', 'find information about Python programming'"
                        }
                    }
                )
                return task
            
            # Determine if it's a news search or general web search
            is_news = any(word in text.lower() for word in ["news", "headlines", "breaking", "recent", "latest", "current events"])
            
            max_results = self._extract_max_results_from_text(text.lower())
            
            if is_news:
                search_response = asyncio.run(self.search_news(query, max_results))
            else:
                search_response = asyncio.run(self.search_web(query, max_results))
            
            # Create successful response
            task.artifacts = [{
                "parts": [{"type": "text", "text": search_response}]
            }]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
        except Exception as e:
            logger.error(f"Error handling search task: {e}", exc_info=True)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={
                    "role": "agent",
                    "content": {
                        "type": "text",
                        "text": f"Sorry, I encountered an error processing your search request: {str(e)}"
                    }
                }
            )
        
        return task

    def _extract_query_from_text(self, text: str) -> Optional[str]:
        """Extract search query from natural language text."""
        # Common patterns for query extraction
        patterns = [
            r'(?:search|find|look up|lookup)\s+(?:for|about|on)?\s*["\']?([^"\']+?)["\']?(?:\s|$|\?|!|\.|,)',
            r'(?:search|find|look up|lookup)\s+(?:for|about|on)?\s*(.+)',
            r'(?:what|how|where|when|why)\s+(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                query = match.group(1).strip().rstrip(',')
                # Clean up common words that might be captured
                query = re.sub(r'\b(search|find|look up|lookup|for|about|on|news|headlines)\b', '', query, flags=re.IGNORECASE).strip()
                if query and len(query) > 1:
                    return query
        
        # Fallback: look for meaningful content after common stop words
        words = text.split()
        meaningful_words = []
        skip_next = False
        
        for i, word in enumerate(words):
            clean_word = re.sub(r'[^\w\s]', '', word)
            if skip_next:
                skip_next = False
                continue
            if clean_word.lower() in ['search', 'find', 'look', 'up', 'for', 'about', 'on', 'please', 'can', 'you']:
                skip_next = clean_word.lower() in ['look', 'can']
                continue
            if clean_word and len(clean_word) > 1:
                meaningful_words.append(clean_word)
        
        if meaningful_words:
            return " ".join(meaningful_words[:6])  # Max 6 words for query
        
        return None

    def _extract_max_results_from_text(self, text: str) -> int:
        """Extract maximum number of results from text query."""
        # Look for specific result numbers
        result_patterns = [
            (r'(\d+)\s*(?:results|entries|items|links)', lambda m: int(m.group(1))),
            (r'(?:show|get|find)\s+(\d+)', lambda m: int(m.group(1))),
            (r'top\s+(\d+)', lambda m: int(m.group(1))),
            (r'first\s+(\d+)', lambda m: int(m.group(1))),
            (r'(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:results|entries|items|links)', 
             lambda m: {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 
                       'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}.get(m.group(1), 5)),
        ]
        
        for pattern, converter in result_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    results = converter(match)
                    return min(max(results, 1), 10)  # Clamp between 1-10 results
                except (ValueError, KeyError):
                    continue
        
        return 5  # Default

    def _format_search_response(self, query: str, data: Dict[str, Any], max_results: int) -> str:
        """Format search results into a readable response."""
        if not data or "error" in data:
            return f"Could not retrieve search results for '{query}'. Please try again."
        
        results = data.get("results", [])
        if not results:
            return f"🔍 No search results found for '{query}'. Please try a different search term."
        
        response = f"🔍 Top {min(max_results, len(results))} search results for **{query}**:\n\n"
        
        for i, result in enumerate(results[:max_results]):
            title = result.get("title", "No Title")
            url = result.get("url", "#")
            snippet = result.get("body", "")
            
            response += f"🔸 **{title}**\n"
            if snippet and len(snippet) > 10:
                snippet_preview = snippet[:200] + "..." if len(snippet) > 200 else snippet
                response += f"   📝 {snippet_preview}\n"
            response += f"   🔗 {url}\n\n"
        
        return response

    def _format_news_response(self, query: str, data: Dict[str, Any], max_results: int) -> str:
        """Format news search results into a readable response."""
        if not data or "error" in data:
            return f"Could not retrieve news results for '{query}'. Please try again."

        results = data.get("results", [])
        if not results:
            return f"📰 No news results found for '{query}'. Please try a different search term."

        response = f"📰 Latest news about **{query}** ({min(max_results, len(results))} articles):\n\n"

        for i, result in enumerate(results[:max_results]):
            title = result.get("title", "No Title")
            url = result.get("url", "#")
            snippet = result.get("body", "")
            
            response += f"📄 **{title}**\n"
            if snippet and len(snippet) > 10:
                snippet_preview = snippet[:250] + "..." if len(snippet) > 250 else snippet
                response += f"   📋 {snippet_preview}\n"
            response += f"   🔗 {url}\n\n"
        
        return response

    async def start_flask_server(self):
        """Start the Flask discovery server in a separate thread."""
        def run_flask():
            try:
                logger.info(f"🌐 Starting Flask discovery server on http://127.0.0.1:{self.flask_port}")
                # CRITICAL: Disable Flask's development features that might cause HTML responses
                self.flask_app.run(
                    host='127.0.0.1', 
                    port=self.flask_port, 
                    debug=False,  # CRITICAL: Must be False
                    use_reloader=False,  # CRITICAL: Must be False
                    threaded=True
                )
            except Exception as e:
                logger.error(f"Flask server error: {e}")
        
        # Start Flask in background thread
        self.flask_thread = threading.Thread(target=run_flask, daemon=True)
        self.flask_thread.start()
        
        # Give Flask time to start and verify it's running
        await asyncio.sleep(3)
        
        # Test the discovery endpoint
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://127.0.0.1:{self.flask_port}/.well-known/agent.json")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info(f"✅ Flask discovery server is running and returning valid JSON")
                        logger.info(f"✅ Agent card discoverable at: http://127.0.0.1:{self.flask_port}/.well-known/agent.json")
                        logger.info(f"📝 Agent name: {data.get('name', 'Unknown')}")
                    except json.JSONDecodeError:
                        logger.error(f"❌ Flask server is returning HTML instead of JSON!")
                        logger.error(f"Response content: {response.text[:200]}...")
                else:
                    logger.warning(f"Flask server responded with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to verify Flask server: {e}")


async def start_web_search_agent():
    """Start the web search agent with proper port separation for discovery."""
    try:
        agent_config = settings.load_agent_config("web_search_agent")
        if not agent_config:
            logger.warning("Web search agent config not found, using defaults.")
    except Exception as e:
        logger.warning(f"Could not load agent config: {e}, using defaults.")

    # Use separate ports for Flask discovery and A2A server
    base_port = 5512
    try:
        base_port = settings.get_agent_port("web_search_agent") or 5512
    except Exception as e:
        logger.warning(f"Could not get agent port: {e}, using default 5512")
    
    # Use separate ports - Flask for discovery, A2A for task processing
    flask_port = find_free_port(base_port)  # Discovery server port
    a2a_port = find_free_port(flask_port + 1)  # A2A server port (different port)
    
    agent = WebSearchAgent()
    agent.flask_port = flask_port
    agent.a2a_port = a2a_port
    
    logger.info(f"🔍 Web Search Agent configuration:")
    logger.info(f"  Flask Discovery Port: {flask_port}")
    logger.info(f"  A2A Server Port: {a2a_port}")
    logger.info(f"  Discovery URL: http://127.0.0.1:{flask_port}/.well-known/agent.json")
    logger.info(f"  A2A URL: http://127.0.0.1:{a2a_port}/a2a")
    
    # Create Flask app for discovery
    agent.flask_app = agent.create_flask_app()
    
    # Start Flask discovery server
    await agent.start_flask_server()
    
    # Start A2A server on different port
    try:
        logger.info(f"🚀 Starting A2A server on port {a2a_port}...")
        await run_server(agent, host="127.0.0.1", port=a2a_port)
    except Exception as e:
        logger.error(f"❌ Error starting A2A server: {e}")
        raise


def main():
    """Main entry point for running the web search agent."""
    logger.info("🔍 Web Search Agent Server Starting...")
    logger.info("=" * 60)
    
    try:
        asyncio.run(start_web_search_agent())
    except KeyboardInterrupt:
        logger.info("🛑 Web Search Agent Server stopped by user")
    except Exception as e:
        logger.error(f"❌ Web Search Agent Server error: {e}", exc_info=True)


# Run the server
if __name__ == "__main__":
    main()