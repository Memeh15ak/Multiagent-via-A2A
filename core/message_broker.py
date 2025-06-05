# core/message_broker.py - Enhanced message broker with proper queue management and consume method

import asyncio
import time
from asyncio import Queue
from typing import Dict, Any, Callable, List, Optional, AsyncGenerator
from loguru import logger
from enum import Enum

class InternalMessageType(Enum):
    USER_QUERY = "InternalMessageType.USER_QUERY"
    QUERY_RESPONSE = "InternalMessageType.QUERY_RESPONSE"
    SYSTEM_STATUS = "InternalMessageType.SYSTEM_STATUS"
    AGENT_STATUS = "InternalMessageType.AGENT_STATUS"
    HEARTBEAT = "InternalMessageType.HEARTBEAT"

class MessageBroker:
    def __init__(self, max_queue_size: int = 1000, message_timeout: float = 30.0):
        self.topics: Dict[str, Queue] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.message_handlers: Dict[str, List[asyncio.Task]] = {}
        self.consumers: Dict[str, List[asyncio.Task]] = {}  # Track active consumers
        self.max_queue_size = max_queue_size
        self.message_timeout = message_timeout
        self._running = False
        self._broker_tasks: List[asyncio.Task] = []
        self.message_stats = {
            "total_published": 0,
            "total_processed": 0,
            "total_failed": 0,
            "topics_created": 0,
            "total_consumed": 0
        }

    async def start(self):
        """Start the message broker"""
        if self._running:
            logger.warning("Message broker is already running")
            return
        
        self._running = True
        logger.info("Message broker started")
        
        # Pre-create standard topics
        for msg_type in InternalMessageType:
            await self._ensure_topic_exists(msg_type.value)
        
        logger.info(f"Message broker initialized with {len(self.topics)} topics")

    async def stop(self):
        """Stop the message broker and clean up"""
        if not self._running:
            return
        
        self._running = False
        logger.info("Stopping message broker...")
        
        # Cancel all running tasks
        for tasks in self.message_handlers.values():
            for task in tasks:
                if not task.done():
                    task.cancel()
        
        # Cancel consumer tasks
        for tasks in self.consumers.values():
            for task in tasks:
                if not task.done():
                    task.cancel()
        
        # Cancel broker tasks
        for task in self._broker_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        all_tasks = []
        for tasks in self.message_handlers.values():
            all_tasks.extend(tasks)
        for tasks in self.consumers.values():
            all_tasks.extend(tasks)
        all_tasks.extend(self._broker_tasks)
        
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Clear data structures
        self.topics.clear()
        self.subscribers.clear()
        self.message_handlers.clear()
        self.consumers.clear()
        self._broker_tasks.clear()
        
        logger.info("Message broker stopped")

    async def _ensure_topic_exists(self, topic: str):
        """Ensure a topic exists, create if it doesn't"""
        if topic not in self.topics:
            self.topics[topic] = Queue(maxsize=self.max_queue_size)
            self.subscribers[topic] = []
            self.message_handlers[topic] = []
            self.consumers[topic] = []
            self.message_stats["topics_created"] += 1
            logger.debug(f"Created topic: {topic}")

    async def publish(self, topic: str, message: Dict[str, Any]):
        """Publish a message to a topic"""
        if not self._running:
            logger.error("Cannot publish message - broker is not running")
            return False
        
        try:
            await self._ensure_topic_exists(topic)
            
            # Add metadata to message
            enriched_message = {
                **message,
                "_broker_timestamp": time.time(),
                "_broker_topic": topic,
                "_broker_id": f"{topic}_{time.time()}_{id(message)}"
            }
            
            # Check if there are any subscribers or consumers
            has_subscribers = bool(self.subscribers.get(topic))
            has_consumers = bool(self.consumers.get(topic))
            
            if not has_subscribers and not has_consumers:
                logger.warning(f"No active subscribers or consumers for topic '{topic}'. Message not delivered.")
                return False
            
            # Put message in queue (non-blocking)
            queue = self.topics[topic]
            try:
                queue.put_nowait(enriched_message)
                self.message_stats["total_published"] += 1
                logger.debug(f"Published message to topic '{topic}': {message}")
                
                # Process messages for this topic if not already processing
                await self._ensure_topic_processing(topic)
                return True
                
            except asyncio.QueueFull:
                logger.error(f"Queue full for topic '{topic}'. Message dropped.")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing message to topic '{topic}': {e}")
            return False

    async def consume(self, topic: str, timeout: float = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Consume messages from a topic using async generator pattern.
        This method yields messages as they become available.
        """
        if not self._running:
            logger.error("Cannot consume messages - broker is not running")
            return
        
        try:
            await self._ensure_topic_exists(topic)
            queue = self.topics[topic]
            
            # Track this consumer
            consumer_task = asyncio.current_task()
            if topic not in self.consumers:
                self.consumers[topic] = []
            self.consumers[topic].append(consumer_task)
            
            logger.info(f"Started consuming messages from topic '{topic}'")
            
            while self._running:
                try:
                    # Use timeout if provided, otherwise use default
                    wait_timeout = timeout if timeout is not None else 1.0
                    
                    # Wait for message with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=wait_timeout)
                    
                    # Update stats
                    self.message_stats["total_consumed"] += 1
                    
                    logger.debug(f"Consumed message from topic '{topic}': {message.get('_broker_id', 'unknown')}")
                    yield message
                    
                except asyncio.TimeoutError:
                    # Timeout is normal - continue or break based on timeout parameter
                    if timeout is not None:
                        # If specific timeout was requested, break on timeout
                        break
                    continue
                    
                except asyncio.CancelledError:
                    logger.info(f"Consumer for topic '{topic}' was cancelled")
                    break
                    
                except Exception as e:
                    logger.error(f"Error consuming message from topic '{topic}': {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error setting up consumer for topic '{topic}': {e}")
        finally:
            # Clean up consumer tracking
            if topic in self.consumers and consumer_task in self.consumers[topic]:
                self.consumers[topic].remove(consumer_task)
            logger.info(f"Stopped consuming messages from topic '{topic}'")

    async def consume_one(self, topic: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Consume a single message from a topic with timeout.
        Returns None if no message is available within timeout.
        """
        if not self._running:
            logger.error("Cannot consume message - broker is not running")
            return None
        
        try:
            await self._ensure_topic_exists(topic)
            queue = self.topics[topic]
            
            # Wait for message with timeout
            message = await asyncio.wait_for(queue.get(), timeout=timeout)
            
            # Update stats
            self.message_stats["total_consumed"] += 1
            
            logger.debug(f"Consumed single message from topic '{topic}': {message.get('_broker_id', 'unknown')}")
            return message
            
        except asyncio.TimeoutError:
            logger.debug(f"No message available in topic '{topic}' within {timeout}s timeout")
            return None
            
        except Exception as e:
            logger.error(f"Error consuming single message from topic '{topic}': {e}")
            return None

    async def _ensure_topic_processing(self, topic: str):
        """Ensure there's a processing task for the topic"""
        if topic not in self.message_handlers:
            self.message_handlers[topic] = []
        
        # Check if we have active processing tasks
        active_tasks = [task for task in self.message_handlers[topic] if not task.done()]
        
        if not active_tasks:
            # Create new processing task
            task = asyncio.create_task(self._process_topic_messages(topic))
            self.message_handlers[topic].append(task)
            self._broker_tasks.append(task)
            logger.debug(f"Started message processing task for topic '{topic}'")

    async def _process_topic_messages(self, topic: str):
        """Process messages for a specific topic"""
        try:
            queue = self.topics[topic]
            
            while self._running:
                try:
                    # Only process if we have subscribers (consumers are handled separately)
                    subscribers = self.subscribers.get(topic, [])
                    if not subscribers:
                        # No subscribers, check if we have consumers
                        consumers = self.consumers.get(topic, [])
                        if not consumers:
                            # No subscribers or consumers, wait and check again
                            await asyncio.sleep(1.0)
                            continue
                        else:
                            # Consumers will handle messages, no need to process here
                            await asyncio.sleep(1.0)
                            continue
                    
                    # Wait for message with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    # Process message with all subscribers
                    await self._process_message(topic, message, subscribers)
                    
                except asyncio.TimeoutError:
                    # Check if we should continue processing
                    if queue.empty() and not self.subscribers.get(topic):
                        logger.debug(f"No messages or subscribers for topic '{topic}', stopping processor")
                        break
                    continue
                    
                except Exception as e:
                    logger.error(f"Error processing message for topic '{topic}': {e}")
                    self.message_stats["total_failed"] += 1
                    
        except Exception as e:
            logger.error(f"Error in topic processor for '{topic}': {e}")
        finally:
            logger.debug(f"Message processor for topic '{topic}' stopped")

    async def _process_message(self, topic: str, message: Dict[str, Any], subscribers: List[Callable]):
        """Process a single message with all subscribers"""
        if not subscribers:
            logger.warning(f"No subscribers for topic '{topic}', message dropped")
            return
        
        # Process message with all subscribers concurrently
        tasks = []
        for subscriber in subscribers:
            task = asyncio.create_task(self._call_subscriber(subscriber, message, topic))
            tasks.append(task)
        
        # Wait for all subscribers to process the message
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful processing
        successful = sum(1 for result in results if not isinstance(result, Exception))
        failed = len(results) - successful
        
        self.message_stats["total_processed"] += successful
        self.message_stats["total_failed"] += failed
        
        if failed > 0:
            logger.warning(f"Topic '{topic}': {successful} successful, {failed} failed subscriber calls")
        else:
            logger.debug(f"Topic '{topic}': Successfully processed by {successful} subscribers")

    async def _call_subscriber(self, subscriber: Callable, message: Dict[str, Any], topic: str):
        """Call a subscriber with error handling"""
        try:
            if asyncio.iscoroutinefunction(subscriber):
                await subscriber(message)
            else:
                subscriber(message)
            return True
        except Exception as e:
            logger.error(f"Error calling subscriber for topic '{topic}': {e}")
            return False

    def subscribe(self, topic: str, callback: Callable):
        """Subscribe to a topic"""
        if not self._running:
            logger.error("Cannot subscribe - broker is not running")
            return False
        
        try:
            asyncio.create_task(self._ensure_topic_exists(topic))
            
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            
            if callback not in self.subscribers[topic]:
                self.subscribers[topic].append(callback)
                logger.info(f"Subscribed to topic '{topic}'. Total subscribers: {len(self.subscribers[topic])}")
                
                # Ensure processing is active for this topic
                asyncio.create_task(self._ensure_topic_processing(topic))
                return True
            else:
                logger.warning(f"Callback already subscribed to topic '{topic}'")
                return False
                
        except Exception as e:
            logger.error(f"Error subscribing to topic '{topic}': {e}")
            return False

    def unsubscribe(self, topic: str, callback: Callable):
        """Unsubscribe from a topic"""
        try:
            if topic in self.subscribers and callback in self.subscribers[topic]:
                self.subscribers[topic].remove(callback)
                logger.info(f"Unsubscribed from topic '{topic}'. Remaining subscribers: {len(self.subscribers[topic])}")
                return True
            else:
                logger.warning(f"Callback not found in subscribers for topic '{topic}'")
                return False
        except Exception as e:
            logger.error(f"Error unsubscribing from topic '{topic}': {e}")
            return False

    def list_topics(self) -> List[str]:
        """List all available topics"""
        return list(self.topics.keys())

    def list_all_topics(self) -> Dict[str, Dict]:
        """List all topics with detailed information"""
        topics_info = {}
        for topic in self.topics:
            queue = self.topics[topic]
            subscribers = self.subscribers.get(topic, [])
            handlers = self.message_handlers.get(topic, [])
            consumers = self.consumers.get(topic, [])
            
            topics_info[topic] = {
                "queue_size": queue.qsize(),
                "max_queue_size": queue.maxsize,
                "subscribers_count": len(subscribers),
                "active_handlers": len([h for h in handlers if not h.done()]),
                "total_handlers": len(handlers),
                "active_consumers": len([c for c in consumers if not c.done()]),
                "total_consumers": len(consumers)
            }
        
        return topics_info

    def get_topic_stats(self, topic: str) -> Optional[Dict]:
        """Get statistics for a specific topic"""
        if topic not in self.topics:
            return None
        
        queue = self.topics[topic]
        subscribers = self.subscribers.get(topic, [])
        handlers = self.message_handlers.get(topic, [])
        consumers = self.consumers.get(topic, [])
        
        return {
            "topic": topic,
            "queue_size": queue.qsize(),
            "max_queue_size": queue.maxsize,
            "subscribers_count": len(subscribers),
            "active_handlers": len([h for h in handlers if not h.done()]),
            "total_handlers": len(handlers),
            "active_consumers": len([c for c in consumers if not c.done()]),
            "total_consumers": len(consumers),
            "queue_full": queue.full(),
            "queue_empty": queue.empty()
        }

    def get_broker_stats(self) -> Dict:
        """Get overall broker statistics"""
        return {
            "running": self._running,
            "total_topics": len(self.topics),
            "total_subscribers": sum(len(subs) for subs in self.subscribers.values()),
            "total_consumers": sum(len(cons) for cons in self.consumers.values()),
            "total_active_handlers": sum(
                len([h for h in handlers if not h.done()]) 
                for handlers in self.message_handlers.values()
            ),
            "total_active_consumers": sum(
                len([c for c in consumers if not c.done()]) 
                for consumers in self.consumers.values()
            ),
            "message_stats": self.message_stats.copy(),
            "topics": self.list_all_topics()
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the message broker"""
        try:
            # Test basic functionality
            test_topic = "health_check_test"
            test_message = {"test": True, "timestamp": time.time()}
            
            # Create a simple subscriber for testing
            test_results = []
            
            def test_subscriber(msg):
                test_results.append(msg)
            
            # Subscribe and publish test message
            self.subscribe(test_topic, test_subscriber)
            await self.publish(test_topic, test_message)
            
            # Wait a bit for processing
            await asyncio.sleep(0.1)
            
            # Test consume functionality
            await self.publish(test_topic, {"consume_test": True})
            consumed_message = await self.consume_one(test_topic, timeout=1.0)
            
            # Check if message was processed
            subscribe_success = len(test_results) > 0
            consume_success = consumed_message is not None
            
            # Clean up
            self.unsubscribe(test_topic, test_subscriber)
            
            return {
                "healthy": subscribe_success and consume_success,
                "running": self._running,
                "subscribe_test_passed": subscribe_success,
                "consume_test_passed": consume_success,
                "stats": self.get_broker_stats(),
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "healthy": False,
                "running": self._running,
                "error": str(e),
                "timestamp": time.time()
            }

# Global instance
message_broker = MessageBroker()