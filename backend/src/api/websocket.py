"""WebSocket endpoint for real-time updates"""

import asyncio
import json
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from ..models.api_models import WebSocketMessage, WebSocketMessageType
from ..services.data_aggregator import IDataAggregator
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and subscriptions"""

    def __init__(self) -> None:
        # Active connections: websocket -> set of subscribed systems
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # System subscriptions: system_name -> set of websockets
        self.system_subscriptions: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a new WebSocket connection

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections[websocket] = set()
        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection

        Args:
            websocket: WebSocket connection
        """
        async with self._lock:
            # Unsubscribe from all systems
            if websocket in self.active_connections:
                subscribed_systems = self.active_connections[websocket]
                for system_name in subscribed_systems:
                    if system_name in self.system_subscriptions:
                        self.system_subscriptions[system_name].discard(websocket)
                        if not self.system_subscriptions[system_name]:
                            del self.system_subscriptions[system_name]

                del self.active_connections[websocket]

        logger.info(
            f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
        )

    async def subscribe(self, websocket: WebSocket, system_name: str) -> None:
        """
        Subscribe a connection to system updates

        Args:
            websocket: WebSocket connection
            system_name: System to subscribe to
        """
        async with self._lock:
            if websocket not in self.active_connections:
                return

            # Add to connection's subscriptions
            self.active_connections[websocket].add(system_name)

            # Add to system's subscribers
            if system_name not in self.system_subscriptions:
                self.system_subscriptions[system_name] = set()
            self.system_subscriptions[system_name].add(websocket)

        logger.info(f"WebSocket subscribed to system: {system_name}")

    async def unsubscribe(self, websocket: WebSocket, system_name: str) -> None:
        """
        Unsubscribe a connection from system updates

        Args:
            websocket: WebSocket connection
            system_name: System to unsubscribe from
        """
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections[websocket].discard(system_name)

            if system_name in self.system_subscriptions:
                self.system_subscriptions[system_name].discard(websocket)
                if not self.system_subscriptions[system_name]:
                    del self.system_subscriptions[system_name]

        logger.info(f"WebSocket unsubscribed from system: {system_name}")

    async def broadcast_to_system(self, system_name: str, message: dict) -> None:
        """
        Broadcast a message to all subscribers of a system

        Args:
            system_name: System name
            message: Message to broadcast
        """
        async with self._lock:
            if system_name not in self.system_subscriptions:
                return

            subscribers = list(self.system_subscriptions[system_name])

        # Send to all subscribers (outside lock to avoid blocking)
        disconnected = []
        for websocket in subscribers:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to websocket: {e}")
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)

    async def send_personal_message(self, websocket: WebSocket, message: dict) -> None:
        """
        Send a message to a specific connection

        Args:
            websocket: WebSocket connection
            message: Message to send
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
            await self.disconnect(websocket)


# Global connection manager
manager = ConnectionManager()

# Dependency injection - set by main.py
_aggregator: Optional[IDataAggregator] = None


def set_aggregator(aggregator: IDataAggregator) -> None:
    """Set the data aggregator for WebSocket endpoint"""
    global _aggregator
    _aggregator = aggregator


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time colonisation updates

    Args:
        websocket: WebSocket connection
    """
    await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                message_type = message.get("type")

                if message_type == "subscribe":
                    system_name = message.get("system_name")
                    if system_name:
                        await manager.subscribe(websocket, system_name)

                        # Send initial data
                        if _aggregator:
                            system_data = await _aggregator.aggregate_by_system(
                                system_name
                            )
                            response = WebSocketMessage(
                                type=WebSocketMessageType.UPDATE,
                                system_name=system_name,
                                data={
                                    "construction_sites": [
                                        site.model_dump()
                                        for site in system_data.construction_sites
                                    ],
                                    "total_sites": system_data.total_sites,
                                    "completed_sites": system_data.completed_sites,
                                    "in_progress_sites": system_data.in_progress_sites,
                                    "completion_percentage": system_data.completion_percentage,
                                },
                                timestamp=datetime.now(timezone.utc).isoformat(),
                            )
                            await manager.send_personal_message(
                                websocket, response.model_dump()
                            )

                elif message_type == "unsubscribe":
                    system_name = message.get("system_name")
                    if system_name:
                        await manager.unsubscribe(websocket, system_name)

                elif message_type == "ping":
                    # Respond with pong
                    pong = WebSocketMessage(
                        type=WebSocketMessageType.PONG,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    await manager.send_personal_message(websocket, pong.model_dump())

            except json.JSONDecodeError:
                error = WebSocketMessage(
                    type=WebSocketMessageType.ERROR, error="Invalid JSON message"
                )
                await manager.send_personal_message(websocket, error.model_dump())

            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                error = WebSocketMessage(type=WebSocketMessageType.ERROR, error=str(e))
                await manager.send_personal_message(websocket, error.model_dump())

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


async def notify_system_update(system_name: str) -> None:
    """
    Notify all subscribers about a system update

    Args:
        system_name: System that was updated
    """
    if _aggregator is None:
        return

    try:
        system_data = await _aggregator.aggregate_by_system(system_name)

        message = WebSocketMessage(
            type=WebSocketMessageType.UPDATE,
            system_name=system_name,
            data={
                "construction_sites": [
                    site.model_dump() for site in system_data.construction_sites
                ],
                "total_sites": system_data.total_sites,
                "completed_sites": system_data.completed_sites,
                "in_progress_sites": system_data.in_progress_sites,
                "completion_percentage": system_data.completion_percentage,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await manager.broadcast_to_system(system_name, message.model_dump())
        logger.debug(f"Notified subscribers of update to {system_name}")

    except Exception as e:
        logger.error(f"Error notifying system update: {e}")


async def notify_global_refresh() -> None:
    """Broadcast a global refresh hint to all connected clients.

    Unlike per-system UPDATE messages, this message is not tied to a system
    subscription; any connected UI can use it to refetch:
      - /api/systems
      - /api/system?name=<current>

    This is primarily used after bulk operations like debug journal reloads or
    configuration changes.
    """
    try:
        message = WebSocketMessage(
            type=WebSocketMessageType.REFRESH,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        payload = message.model_dump()

        # Snapshot connections to avoid holding the manager lock while sending.
        async with manager._lock:  # noqa: SLF001
            websockets = list(manager.active_connections.keys())

        for websocket in websockets:
            await manager.send_personal_message(websocket, payload)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Error broadcasting global refresh: {exc}")
