"""
WebSocket Manager for real-time alert broadcasting.
Handles WebSocket connections and broadcasts alert events to connected browsers
with smart deduplication to prevent false alerts on reconnection.
"""
import asyncio
import logging
from typing import Set, Dict, Any
from fastapi import WebSocket
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time dashboard updates.

    Note: Audio alerts are now handled via client-side polling of /api/v1/alerts/state
    for better reliability across page refreshes, multiple tabs, and mobile reconnections.
    WebSocket is kept for real-time non-audio updates (status changes, etc.).
    """

    def __init__(self):
        # WebSocket connection management
        self.active_connections: Dict[str, WebSocket] = {}  # client_id -> WebSocket
        self._lock = asyncio.Lock()

    def _generate_client_id(self) -> str:
        """Generate a unique client ID for tracking."""
        return str(uuid.uuid4())

    async def connect(self, websocket: WebSocket) -> str:
        """
        Accept and register a new WebSocket connection.

        Returns:
            client_id: Unique identifier for this client
        """
        await websocket.accept()

        # Generate unique client ID
        client_id = self._generate_client_id()

        async with self._lock:
            self.active_connections[client_id] = websocket

        logger.info(f"✅ WebSocket client {client_id[:8]} connected. Total connections: {len(self.active_connections)}")
        return client_id

    async def disconnect(self, client_id: str):
        """Unregister a WebSocket connection."""
        async with self._lock:
            self.active_connections.pop(client_id, None)

        logger.info(f"❌ WebSocket client {client_id[:8]} disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast_alert(self, event_type: str, target_name: str, target_id: str,
                            audio_filename: str, message: str):
        """
        Broadcast an alert event to connected clients.

        Note: Audio playback is now handled by client-side polling. This WebSocket
        broadcast is kept for backwards compatibility and real-time dashboard updates.

        Args:
            event_type: Type of alert ('threshold_reached', 'recovered', 'alert_repeat')
            target_name: Name of the target device
            target_id: ID of the target
            audio_filename: Audio file to play
            message: Alert message
        """
        if not self.active_connections:
            logger.debug("No WebSocket clients connected for alert broadcast")
            return

        payload = {
            "type": "alert_event",
            "event_type": event_type,
            "target_name": target_name,
            "target_id": target_id,
            "audio_filename": audio_filename,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Send to all connected clients (no deduplication needed)
        sent_count = 0
        disconnected = []

        async with self._lock:
            for client_id, connection in list(self.active_connections.items()):
                try:
                    await connection.send_json(payload)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to WebSocket client {client_id[:8]}: {e}")
                    disconnected.append(client_id)

            # Clean up disconnected clients
            for client_id in disconnected:
                self.active_connections.pop(client_id, None)

        if sent_count > 0:
            logger.info(f"📡 Broadcasted alert to {sent_count} client(s): {target_name}")
        else:
            logger.debug(f"No WebSocket clients to broadcast {target_name}")

        if disconnected:
            logger.info(f"Removed {len(disconnected)} disconnected client(s)")

    async def send_heartbeat(self):
        """Send heartbeat to all connected clients to detect disconnections."""
        if not self.active_connections:
            return

        payload = {
            "type": "heartbeat",
            "timestamp": datetime.utcnow().isoformat()
        }

        disconnected = []
        async with self._lock:
            for client_id, connection in list(self.active_connections.items()):
                try:
                    await connection.send_json(payload)
                except Exception:
                    disconnected.append(client_id)

            for client_id in disconnected:
                self.active_connections.pop(client_id, None)

    def get_connection_count(self) -> int:
        """Get the number of active WebSocket connections."""
        return len(self.active_connections)

    def get_status(self) -> Dict[str, Any]:
        """Get WebSocket manager status."""
        return {
            "active_connections": len(self.active_connections),
            "active_alerts": len(self.active_alerts),
            "enabled": True
        }
