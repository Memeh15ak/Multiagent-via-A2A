# server/websocket_handler.py - Updated WebSocket handler with improved heartbeat and connection management

import asyncio
import json
import time
import uuid
from typing import Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

class ConnectionManager:
    def __init__(self, heartbeat_interval: float = 30.0, ping_timeout: float = 10.0):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_heartbeats: Dict[str, float] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self.heartbeat_interval = heartbeat_interval
        self.ping_timeout = ping_timeout
        self._heartbeat_running = False
        self._main_heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket) -> str:
        """Accept WebSocket connection and return user ID"""
        await websocket.accept()
        user_id = str(uuid.uuid4())
        
        self.active_connections[user_id] = websocket
        self.user_heartbeats[user_id] = time.time()
        
        # Start heartbeat for this connection
        await self._start_heartbeat_for_user(user_id)
        
        # Start main heartbeat loop if not already running
        if not self._heartbeat_running:
            await self._start_main_heartbeat()
        
        logger.info(f"WebSocket connected. User ID: {user_id}. Total connections: {len(self.active_connections)}")
        return user_id

    def disconnect(self, websocket: WebSocket):
        """Disconnect WebSocket and cleanup"""
        user_id = None
        # Find user_id by websocket
        for uid, ws in self.active_connections.items():
            if ws == websocket:
                user_id = uid
                break
        
        if user_id:
            self._cleanup_user_connection(user_id)
            logger.info(f"WebSocket disconnected. User ID: {user_id}. Remaining connections: {len(self.active_connections)}")
        
        # Stop main heartbeat if no connections remain
        if not self.active_connections and self._heartbeat_running:
            self._stop_main_heartbeat()

    def _cleanup_user_connection(self, user_id: str):
        """Clean up all resources for a user connection"""
        # Remove from active connections
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        
        # Remove heartbeat timestamp
        if user_id in self.user_heartbeats:
            del self.user_heartbeats[user_id]
        
        # Cancel and remove heartbeat task
        if user_id in self.heartbeat_tasks:
            task = self.heartbeat_tasks[user_id]
            if not task.done():
                task.cancel()
            del self.heartbeat_tasks[user_id]

    async def disconnect_all(self):
        """Disconnect all WebSocket connections"""
        logger.info(f"Disconnecting all {len(self.active_connections)} connections...")
        
        # Stop main heartbeat
        self._stop_main_heartbeat()
        
        # Disconnect all connections
        for user_id in list(self.active_connections.keys()):
            try:
                websocket = self.active_connections[user_id]
                await websocket.close()
                self._cleanup_user_connection(user_id)
            except Exception as e:
                logger.error(f"Error disconnecting user {user_id}: {e}")
        
        logger.info("All connections disconnected")

    async def send_personal_message(self, message: str, user_id: str):
        """Send message to specific user"""
        websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_text(message)
                return True
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                self._cleanup_user_connection(user_id)
                return False
        return False

    async def broadcast(self, message: str, exclude_user: Optional[str] = None):
        """Broadcast message to all connected users"""
        if not self.active_connections:
            return
        
        disconnected_users = []
        for user_id, websocket in self.active_connections.items():
            if exclude_user and user_id == exclude_user:
                continue
            
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
                disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            self._cleanup_user_connection(user_id)

    async def _start_main_heartbeat(self):
        """Start the main heartbeat loop"""
        if self._heartbeat_running:
            return
        
        self._heartbeat_running = True
        self._main_heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Main heartbeat loop started")

    def _stop_main_heartbeat(self):
        """Stop the main heartbeat loop"""
        self._heartbeat_running = False
        if self._main_heartbeat_task and not self._main_heartbeat_task.done():
            self._main_heartbeat_task.cancel()
        logger.info("Main heartbeat loop stopped")

    async def _start_heartbeat_for_user(self, user_id: str):
        """Start individual heartbeat task for a user"""
        if user_id in self.heartbeat_tasks:
            # Cancel existing task
            task = self.heartbeat_tasks[user_id]
            if not task.done():
                task.cancel()
        
        # Create new heartbeat task for this user
        task = asyncio.create_task(self._user_heartbeat_loop(user_id))
        self.heartbeat_tasks[user_id] = task

    async def _user_heartbeat_loop(self, user_id: str):
        """Individual heartbeat loop for a specific user"""
        try:
            while user_id in self.active_connections and self._heartbeat_running:
                websocket = self.active_connections.get(user_id)
                if not websocket:
                    break
                
                try:
                    # Send ping
                    ping_message = {
                        "type": "ping",
                        "timestamp": time.time(),
                        "user_id": user_id
                    }
                    await websocket.send_text(json.dumps(ping_message))
                    logger.debug(f"Sent heartbeat ping to user {user_id}")
                    
                    # Wait for next heartbeat
                    await asyncio.sleep(self.heartbeat_interval)
                    
                    # Check if user responded recently (within timeout)
                    last_heartbeat = self.user_heartbeats.get(user_id, 0)
                    if time.time() - last_heartbeat > (self.heartbeat_interval + self.ping_timeout):
                        logger.warning(f"User {user_id} failed heartbeat check - disconnecting")
                        await self._force_disconnect_user(user_id, "heartbeat_timeout")
                        break
                        
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected during heartbeat for user {user_id}")
                    break
                except Exception as e:
                    logger.error(f"Error in heartbeat for user {user_id}: {e}")
                    await self._force_disconnect_user(user_id, "heartbeat_error")
                    break
                    
        except asyncio.CancelledError:
            logger.debug(f"Heartbeat task cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Unexpected error in heartbeat loop for user {user_id}: {e}")

    async def _heartbeat_loop(self):
        """Main heartbeat monitoring loop"""
        try:
            while self._heartbeat_running:
                if self.active_connections:
                    logger.debug(f"Heartbeat sent to {len(self.active_connections)} connections")
                
                await asyncio.sleep(self.heartbeat_interval)
                
        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Error in main heartbeat loop: {e}")

    async def _force_disconnect_user(self, user_id: str, reason: str):
        """Force disconnect a user with a specific reason"""
        try:
            websocket = self.active_connections.get(user_id)
            if websocket:
                # Send disconnect notification
                disconnect_message = {
                    "type": "disconnect",
                    "reason": reason,
                    "timestamp": time.time()
                }
                try:
                    await websocket.send_text(json.dumps(disconnect_message))
                except:
                    pass  # Ignore errors when sending disconnect message
                
                # Close connection
                await websocket.close(code=1011, reason=reason)
            
            # Clean up
            self._cleanup_user_connection(user_id)
            logger.info(f"Force disconnected user {user_id} due to: {reason}")
            
        except Exception as e:
            logger.error(f"Error force disconnecting user {user_id}: {e}")

    def update_user_heartbeat(self, user_id: str):
        """Update last heartbeat timestamp for user"""
        if user_id in self.active_connections:
            self.user_heartbeats[user_id] = time.time()
            logger.debug(f"Updated heartbeat for user {user_id}")

    def get_connection_stats(self) -> Dict:
        """Get connection statistics"""
        current_time = time.time()
        stats = {
            "total_connections": len(self.active_connections),
            "heartbeat_running": self._heartbeat_running,
            "heartbeat_interval": self.heartbeat_interval,
            "ping_timeout": self.ping_timeout,
            "users": {}
        }
        
        for user_id in self.active_connections:
            last_heartbeat = self.user_heartbeats.get(user_id, 0)
            stats["users"][user_id] = {
                "last_heartbeat": last_heartbeat,
                "seconds_since_heartbeat": current_time - last_heartbeat,
                "has_heartbeat_task": user_id in self.heartbeat_tasks
            }
        
        return stats

# Global instance
websocket_manager = ConnectionManager()