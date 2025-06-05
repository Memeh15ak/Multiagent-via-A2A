# agents/news_agent/news_agent.py - FIXED version with proper Flask/A2A integration
from python_a2a import A2AServer, skill, agent, run_server, TaskStatus, TaskState
from flask import Flask, jsonify, request
from loguru import logger
import asyncio
import json
import re
from typing import Dict, Any, Optional
import threading
import time

from agents.news_agent.news_client import NewsAPIClient
from config.settings import settings
from protocols.communication import comm_manager


@agent(
    name="News Agent",
    description="Fetches latest news articles by category, keyword, or country",
    version="1.0.0"
)
class NewsAgent(A2AServer):
    
    def __init__(self):
        """Initialize the news agent with API client."""
        super().__init__()
        self.news_client = NewsAPIClient(settings.NEWS_API_KEY, comm_manager)
        self.flask_app = None
        self.flask_port = None
        self.a2a_port = None
        logger.info("NewsAgent initialized with decorator-based A2A protocol.")
    
    def create_flask_app(self):
        """Create Flask app for HTTP endpoints with proper JSON responses."""
        app = Flask(__name__)
        
        # Disable template auto-reloading and set JSON as default
        app.config['TEMPLATES_AUTO_RELOAD'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
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
            """Standard A2A discovery endpoint."""
            response = jsonify(agent_card)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/a2a', methods=['GET'])
        def a2a_endpoint():
            """A2A protocol endpoint."""
            response = jsonify(agent_card)
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
                "agent": "News Agent",
                "version": "1.0.0",
                "timestamp": time.time(),
                "ports": {
                    "flask": self.flask_port,
                    "a2a": self.a2a_port
                }
            }
            response = jsonify(health_data)
            response.headers['Content-Type'] = 'application/json'
            return response
        
        @app.route('/test', methods=['GET'])
        def test_endpoint():
            """Test endpoint for diagnostics."""
            test_data = {
                "message": "News Agent is running",
                "agent": agent_card,
                "test_time": time.time()
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
            agent_config = settings.load_agent_config("news_agent")
            base_port = settings.get_agent_port("news_agent") or 5313
            
            # Use Flask port for external access
            flask_port = base_port
            base_url = f"http://127.0.0.1:{flask_port}"
            
            return {
                "id": "news_agent_001",
                "name": "News Agent",
                "description": "Fetches latest news articles by category, keyword, or country",
                "url": base_url,
                "a2a_endpoint": f"{base_url}/a2a",
                "version": "1.0.0",
                "type": "agent",
                "protocol": "a2a",
                "capabilities": {
                    "streaming": False,
                    "pushNotifications": False
                },
                "endpoints": {
                    "discovery": f"{base_url}/.well-known/agent.json",
                    "a2a": f"{base_url}/a2a",
                    "task": f"{base_url}/task",
                    "status": f"{base_url}/status",
                    "health": f"{base_url}/health",
                    "test": f"{base_url}/test"
                },
                "skills": [
                    {    
                        "id": "get_latest_news",
                        "name": "Get Latest News",
                        "description": "Get latest news articles by category, keyword, or country",
                        "tags": ["news", "articles", "headlines", "current"],
                        "parameters": {
                            "category": {
                                "type": "string",
                                "description": "News category (business, entertainment, general, health, science, sports, technology)",
                                "required": False
                            },
                            "keyword": {
                                "type": "string",
                                "description": "Search keyword for news articles",
                                "required": False
                            },
                            "country": {
                                "type": "string",
                                "description": "Country code (e.g., us, uk, ca, au)",
                                "required": False,
                                "default": "us"
                            }
                        }
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error creating agent card: {e}")
            # Return a minimal agent card if config fails
            return {
                "id": "news_agent_001",
                "name": "News Agent",
                "description": "Fetches latest news articles by category, keyword, or country",
                "url": "http://127.0.0.1:5313",
                "a2a_endpoint": "http://127.0.0.1:5313",
                "version": "1.0.0",
                "type": "agent",
                "protocol": "a2a",
                "status": "error",
                "error": str(e)
            }
    
    @skill(
        name="Get Latest News",
        description="Get latest news articles by category, keyword, or country",
        tags=["news", "articles", "headlines", "current"]
    )
    async def get_latest_news(self, category: Optional[str] = None, keyword: Optional[str] = None, country: str = "us") -> str:
        """Get latest news articles."""
        try:
            logger.info(f"Getting news - category: {category}, keyword: {keyword}, country: {country}")
            
            if not category and not keyword:
                return "Please specify either a category or keyword to search for news."
            
            news_data = await self.news_client.get_top_headlines(category=category, q=keyword, country=country)
            return self._format_news_response(category, keyword, country, news_data)
        except Exception as e:
            logger.error(f"Error getting news: {e}")
            return f"Sorry, I couldn't get news information. Please try again."

    def handle_task(self, task):
        """Handle incoming A2A tasks with natural language processing."""
        try:
            # Extract message content
            message_data = task.message or {}
            content = message_data.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else ""
            
            logger.info(f"NewsAgent received task with text: {text}")
            
            if not text:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent", 
                        "content": {
                            "type": "text", 
                            "text": "Please ask me about news! Examples: 'Get technology news', 'Latest news about AI', 'Sports news from UK'"
                        }
                    }
                )
                return task
            
            # Parse the request
            category = self._extract_category_from_text(text.lower())
            keyword = self._extract_keyword_from_text(text.lower())
            country = self._extract_country_from_text(text.lower())
            
            if not category and not keyword:
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent",
                        "content": {
                            "type": "text",
                            "text": "Please specify a news category or keyword. Examples: 'technology news', 'news about climate change', 'business headlines'"
                        }
                    }
                )
                return task
            
            # Get news
            news_response = asyncio.run(self.get_latest_news(category, keyword, country))
            
            # Create successful response
            task.artifacts = [{
                "parts": [{"type": "text", "text": news_response}]
            }]
            task.status = TaskStatus(state=TaskState.COMPLETED)
            
        except Exception as e:
            logger.error(f"Error handling news task: {e}", exc_info=True)
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={
                    "role": "agent",
                    "content": {
                        "type": "text",
                        "text": f"Sorry, I encountered an error processing your news request: {str(e)}"
                    }
                }
            )
        
        return task

    def _extract_category_from_text(self, text: str) -> Optional[str]:
        """Extract news category from text."""
        categories = {
            'business': ['business', 'finance', 'economy', 'market', 'stock', 'trade'],
            'entertainment': ['entertainment', 'celebrity', 'movie', 'music', 'show', 'film'],
            'general': ['general', 'world', 'global', 'international'],
            'health': ['health', 'medical', 'medicine', 'covid', 'pandemic', 'wellness'],
            'science': ['science', 'research', 'study', 'discovery', 'scientific'],
            'sports': ['sports', 'football', 'basketball', 'soccer', 'tennis', 'olympics', 'game'],
            'technology': ['technology', 'tech', 'ai', 'artificial intelligence', 'computer', 'software', 'digital']
        }
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        
        return None

    def _extract_keyword_from_text(self, text: str) -> Optional[str]:
        """Extract search keyword from text."""
        # Look for "about X" or "on X" patterns
        patterns = [
            r'(?:about|on|regarding)\s+([a-zA-Z\s]+?)(?:\s|$|\?|!|\.)',
            r'news\s+([a-zA-Z\s]+?)(?:\s|$|\?|!|\.)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                keyword = match.group(1).strip()
                # Clean up common words
                keyword = re.sub(r'\b(news|latest|recent|today|headlines)\b', '', keyword, flags=re.IGNORECASE).strip()
                if keyword and len(keyword) > 2:
                    return keyword
        
        return None

    def _extract_country_from_text(self, text: str) -> str:
        """Extract country code from text."""
        countries = {
            'us': ['usa', 'america', 'united states', 'us'],
            'uk': ['uk', 'britain', 'united kingdom', 'england'],
            'ca': ['canada', 'canadian'],
            'au': ['australia', 'australian'],
            'de': ['germany', 'german'],
            'fr': ['france', 'french'],
            'in': ['india', 'indian'],
            'jp': ['japan', 'japanese'],
            'br': ['brazil', 'brazilian'],
            'cn': ['china', 'chinese']
        }
        
        for code, names in countries.items():
            if any(name in text for name in names):
                return code
        
        return "us"  # Default

    def _format_news_response(self, category: Optional[str], keyword: Optional[str], country: str, data: Dict[str, Any]) -> str:
        """Format news response."""
        articles = data.get("articles", [])
        if not articles:
            search_params = []
            if category:
                search_params.append(f"category '{category}'")
            if keyword:
                search_params.append(f"keyword '{keyword}'")
            return f"📰 No news articles found for {' and '.join(search_params)} in {country.upper()}."

        search_desc = ""
        if category and keyword:
            search_desc = f"'{keyword}' in {category} category"
        elif category:
            search_desc = f"{category} category"
        elif keyword:
            search_desc = f"'{keyword}'"
        
        response_lines = [f"📰 Latest news for {search_desc} ({country.upper()}):\n"]
        
        for i, article in enumerate(articles[:5]):  # Limit to top 5 articles
            title = article.get("title", "No Title")
            source = article.get("source", {}).get("name", "Unknown Source")
            url = article.get("url", "#")
            description = article.get("description", "")
            
            response_lines.append(f"🔸 **{title}**")
            response_lines.append(f"   📍 Source: {source}")
            if description and len(description) > 10:
                response_lines.append(f"   📝 {description[:150]}...")
            response_lines.append(f"   🔗 {url}")
            response_lines.append("")
        
        return "\n".join(response_lines)


async def start_news_agent():
    """Start the news agent with separate Flask and A2A servers."""
    try:
        agent_config = settings.load_agent_config("news_agent")
        if not agent_config:
            logger.warning("News agent config not found, using defaults.")
    except Exception as e:
        logger.warning(f"Could not load agent config: {e}, using defaults.")

    base_port = None
    try:
        base_port = settings.get_agent_port("news_agent") or 5313
    except Exception as e:
        logger.warning(f"Could not get agent port: {e}, using default 5003")
        base_port = 5313
    
    # Use same port for Flask (for discovery) and A2A communication
    flask_port = base_port
    a2a_port = base_port + 100  # Use different port for A2A server to avoid conflicts
    
    agent = NewsAgent()
    agent.flask_port = flask_port
    agent.a2a_port = a2a_port
    
    logger.info(f"News Agent configuration:")
    logger.info(f"  Flask (Discovery) Port: {flask_port}")
    logger.info(f"  A2A Server Port: {a2a_port}")
    
    # Create and start Flask app for discovery
    flask_app = agent.create_flask_app()
    
    def run_flask():
        try:
            logger.info(f"Starting Flask discovery server on port {flask_port}")
            flask_app.run(
                host='127.0.0.1', 
                port=flask_port, 
                debug=False, 
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Flask server error: {e}")
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Give Flask time to start
    await asyncio.sleep(2)
    logger.info(f"✅ Flask discovery server started on http://127.0.0.1:{flask_port}")
    
    # Start A2A server on different port
    try:
        logger.info(f"Starting A2A server on port {a2a_port}...")
        await run_server(agent, host="127.0.0.1", port=a2a_port)
    except Exception as e:
        logger.error(f"Error starting A2A server: {e}")


def main():
    """Main entry point for running the news agent."""
    logger.info("📰 News Agent Server Starting...")
    logger.info("=" * 50)
    
    try:
        asyncio.run(start_news_agent())
    except KeyboardInterrupt:
        logger.info("🛑 News Agent Server stopped by user")
    except Exception as e:
        logger.error(f"❌ News Agent Server error: {e}", exc_info=True)


# Run the server
if __name__ == "__main__":
    main()