"""In-memory registry of active WebSocket connections with broadcast support."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from app.models.player import Player, PlayerStatus

_ALLOWED_PLAYER_FIELDS = frozenset({"display_name", "status", "current_room", "is_ready"})


class ConnectionManager:
    """Tracks accepted WebSocket connections and fans out messages."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._players: dict[str, Player] = {}
        self._subscriptions: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    async def _send(websocket: WebSocket, message: str | dict[str, Any]) -> None:
        if isinstance(message, dict):
            await websocket.send_json(message)
        else:
            await websocket.send_text(message)

    async def connect(self, websocket: WebSocket) -> str:
        """Accept the socket, register it, and return a stable connection id."""
        async with self._lock:
            for cid, existing in self._connections.items():
                if existing is websocket:
                    return cid
        await websocket.accept()
        async with self._lock:
            for cid, existing in self._connections.items():
                if existing is websocket:
                    return cid
            connection_id = str(uuid4())
            self._connections[connection_id] = websocket
            self._players[connection_id] = Player(
                id=connection_id,
                display_name="",
                status=PlayerStatus.IDLE,
                current_room=None,
            )
            return connection_id

    async def set_subscription(self, connection_id: str, scope: str, scope_id: str) -> None:
        """Attach a connection to a logical broadcast scope."""
        async with self._lock:
            if connection_id not in self._connections:
                return
            subscriptions = self._subscriptions.setdefault(connection_id, {})
            subscriptions[scope] = scope_id

    async def clear_subscription(self, connection_id: str, scope: str | None = None) -> None:
        """Remove a subscription for a connection, or all subscriptions."""
        async with self._lock:
            if scope is None:
                self._subscriptions.pop(connection_id, None)
                return

            subscriptions = self._subscriptions.get(connection_id)
            if subscriptions is None:
                return
            subscriptions.pop(scope, None)
            if not subscriptions:
                self._subscriptions.pop(connection_id, None)

    async def disconnect(self, connection_id: str) -> None:
        """Remove a connection if present (idempotent)."""
        async with self._lock:
            self._connections.pop(connection_id, None)
            self._players.pop(connection_id, None)
            self._subscriptions.pop(connection_id, None)

    async def get_player(self, player_id: str) -> Player | None:
        """Return the player for a connection id, if any."""
        async with self._lock:
            return self._players.get(player_id)

    async def update_player(self, player_id: str, **kwargs: Any) -> Player | None:
        """Merge allowed fields into the player record; unknown keys are ignored."""
        async with self._lock:
            current = self._players.get(player_id)
            if current is None:
                return None
            data = current.model_dump()
            for key, value in kwargs.items():
                if key in _ALLOWED_PLAYER_FIELDS:
                    data[key] = value
            updated = Player(**data)
            self._players[player_id] = updated
            return updated

    async def send_personal_message(
        self,
        connection_id: str,
        message: str | dict[str, Any],
    ) -> None:
        """Send a message to a single client; no-op if the id is unknown."""
        async with self._lock:
            websocket = self._connections.get(connection_id)
        if websocket is None:
            return
        try:
            await self._send(websocket, message)
        except Exception:
            await self.disconnect(connection_id)

    async def broadcast(self, message: str | dict[str, Any]) -> None:
        """Send a message to every active connection; drop broken sockets."""
        async with self._lock:
            snapshot = list(self._connections.items())
        dead: list[str] = []
        for connection_id, websocket in snapshot:
            try:
                await self._send(websocket, message)
            except Exception:
                dead.append(connection_id)
        for connection_id in dead:
            await self.disconnect(connection_id)

    async def broadcast_to_scope(
        self,
        scope: str,
        scope_id: str,
        message: str | dict[str, Any],
    ) -> None:
        """Send a message to all connections subscribed to a scope."""
        async with self._lock:
            snapshot = [
                (connection_id, websocket)
                for connection_id, websocket in self._connections.items()
                if self._subscriptions.get(connection_id, {}).get(scope) == scope_id
            ]
        dead: list[str] = []
        for connection_id, websocket in snapshot:
            try:
                await self._send(websocket, message)
            except Exception:
                dead.append(connection_id)
        for connection_id in dead:
            await self.disconnect(connection_id)

    async def reset(self) -> None:
        """Clear all connection state (used by tests)."""
        async with self._lock:
            self._connections.clear()
            self._players.clear()
            self._subscriptions.clear()


connection_manager = ConnectionManager()
