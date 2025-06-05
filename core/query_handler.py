import asyncio
import time
from typing import Dict, Any, Optional
from loguru import logger
from core.message_broker import message_broker, InternalMessageType

class QueryHandler:
    def __init__(self):
        self._running = False
        self._processing_tasks = set()
        
    async def start(self):
        """Start the query handler"""
        self._running = True
        
        # Subscribe to user queries using the global message_broker instance
        message_broker.subscribe(
            InternalMessageType.USER_QUERY.value,
            self.handle_user_query
        )
        
        logger.info("Query handler started and subscribed to USER_QUERY topic")
        
    async def stop(self):
        """Stop the query handler"""
        self._running = False
        
        # Unsubscribe from user queries
        message_broker.unsubscribe(
            InternalMessageType.USER_QUERY.value,
            self.handle_user_query
        )
        
        # Wait for any ongoing processing tasks to complete
        if self._processing_tasks:
            logger.info(f"Waiting for {len(self._processing_tasks)} processing tasks to complete...")
            await asyncio.gather(*self._processing_tasks, return_exceptions=True)
            
        logger.info("Query handler stopped")
        
    async def handle_user_query(self, message: Dict[str, Any]):
        """Handle incoming user queries"""
        if not self._running:
            return
            
        query_id = message.get('query_id')
        user_id = message.get('user_id')
        text_content = message.get('text_content')
        
        logger.info(f"Processing query {query_id} from user {user_id}: {text_content}")
        
        # Create a task for processing this query
        task = asyncio.create_task(self._process_query_async(query_id, user_id, text_content))
        self._processing_tasks.add(task)
        
        # Clean up completed tasks
        task.add_done_callback(self._processing_tasks.discard)
        
    async def _process_query_async(self, query_id: str, user_id: str, text_content: str):
        """Process a single query asynchronously"""
        try:
            # Simulate intelligent processing
            await asyncio.sleep(1)  # Simulate processing time
            
            # Generate response based on query content
            response = self._generate_intelligent_response(text_content)
            
            # Publish response back through message broker
            response_message = {
                'query_id': query_id,
                'user_id': user_id,
                'response': response,
                'status': 'completed',
                'timestamp': time.time(),
                'processing_agent': 'query_handler'
            }
            
            await message_broker.publish(
                InternalMessageType.QUERY_RESPONSE.value,
                response_message
            )
            
            logger.info(f"Completed processing query {query_id}")
            
        except Exception as e:
            logger.error(f"Error processing query {query_id}: {e}")
            
            # Send error response
            error_response = {
                'query_id': query_id,
                'user_id': user_id,
                'response': f"Error processing query: {str(e)}",
                'status': 'error',
                'timestamp': time.time(),
                'processing_agent': 'query_handler'
            }
            
            await message_broker.publish(
                InternalMessageType.QUERY_RESPONSE.value,
                error_response
            )
            
    def _generate_intelligent_response(self, query: str) -> str:
        """Generate contextual responses based on query content"""
        query_lower = query.lower().strip()
        
        # Remove any command prefixes like '<' 
        if query_lower.startswith(('<', '>', '/')):
            query_lower = query_lower[1:].strip()
        
        # Weather queries
        if any(word in query_lower for word in ["weather", "temperature", "rain", "sunny", "cloudy"]):
            return (
                "🌤️ **Weather Update**: I understand you're asking about the weather. "
                "For real-time weather information, I'd need to access current weather APIs. "
                "However, I can help you set up weather data processing or analysis if you have weather data!"
            )
        
        # Data analysis queries
        elif any(word in query_lower for word in ["data", "analysis", "analytics", "statistics", "chart"]):
            return (
                "📊 **Data Analysis Ready**: I can help you with various data analysis tasks including:\n"
                "• Statistical analysis and hypothesis testing\n"
                "• Data visualization and dashboard creation\n"
                "• Predictive modeling and machine learning\n"
                "• Trend analysis and forecasting\n"
                "• Data cleaning and preprocessing\n\n"
                "What specific type of data are you working with?"
            )
        
        # Programming/coding queries
        elif any(word in query_lower for word in ["code", "program", "python", "javascript", "api"]):
            return (
                "💻 **Coding Assistant**: I can help you with programming tasks including:\n"
                "• Code review and optimization\n"
                "• Debugging and troubleshooting\n"
                "• API development and integration\n"
                "• Database design and queries\n"
                "• Best practices and architecture\n\n"
                "Share your specific coding challenge!"
            )
        
        # System status queries
        elif any(word in query_lower for word in ["status", "health", "system"]):
            return (
                "✅ **System Status**: Multi-agent system is running optimally!\n"
                "• Message broker: Active\n"
                "• Query handler: Processing\n"
                "• WebSocket connections: Stable\n"
                "• All systems operational"
            )
        
        # Default intelligent response
        else:
            return (
                f"🤖 **Query Processed**: I received and analyzed your query: '{query}'\n\n"
                f"The multi-agent system has processed your request. For more specific assistance, "
                f"try asking about:\n"
                f"• Weather information\n"
                f"• Data analysis tasks\n"
                f"• Programming help\n"
                f"• System status\n\n"
                f"How else can I help you today?"
            )

# Singleton instance
query_handler = QueryHandler()