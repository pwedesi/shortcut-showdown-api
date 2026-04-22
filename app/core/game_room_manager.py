"""In-memory game room registry; gameplay is isolated per room."""

from __future__ import annotations

import asyncio

from app.core.connection_manager import connection_manager
from app.models.game_room import GameRoom
from app.models.player import PlayerStatus


class GameRoomManager:
    """Tracks active game rooms and keeps player fields in sync on disconnect."""

    def __init__(self) -> None:
        self._rooms: dict[str, GameRoom] = {}
        self._lock = asyncio.Lock()

    async def register_room(self, room: GameRoom) -> None:
        """Insert a room (caller must not duplicate an existing id)."""
        async with self._lock:
            self._rooms[room.id] = room

    async def get_room(self, room_id: str) -> GameRoom | None:
        """Return a game room by id, or None if missing."""
        async with self._lock:
            return self._rooms.get(room_id)

    async def remove_player_from_all_rooms(self, player_id: str) -> None:
        """Remove the player from any game room (disconnect). Deletes empty rooms."""
        removed_from: str | None = None

        async with self._lock:
            for rid, room in list(self._rooms.items()):
                if player_id not in room.players:
                    continue
                removed_from = rid
                new_players = tuple(p for p in room.players if p != player_id)
                if not new_players:
                    del self._rooms[rid]
                else:
                    self._rooms[rid] = GameRoom(
                        id=room.id,
                        players=new_players,
                        game_state=dict(room.game_state),
                        locked=room.locked,
                    )
                break

        if removed_from is None:
            return

        from app.core.game_engine import game_engine

        await game_engine.resolve_forfeit(removed_from, player_id)

        player = await connection_manager.get_player(player_id)
        if player is None:
            return
        if player.current_room == removed_from:
            await connection_manager.update_player(
                player_id,
                status=PlayerStatus.IDLE,
                current_room=None,
            )

    async def reset(self) -> None:
        """Clear all game rooms (used by tests)."""
        async with self._lock:
            self._rooms.clear()


game_room_manager = GameRoomManager()
