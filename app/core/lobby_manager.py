"""In-memory lobby registry with capacity limits."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.core.config import get_settings
from app.core.connection_manager import connection_manager
from app.models.lobby import Lobby, LobbyStatus
from app.models.player import PlayerStatus


class LobbyManager:
    """Tracks lobbies and keeps `Player` lobby fields in sync when possible."""

    def __init__(self) -> None:
        self._lobbies: dict[str, Lobby] = {}
        self._lock = asyncio.Lock()

    def _status_for_count(self, count: int, max_players: int) -> LobbyStatus:
        return LobbyStatus.FULL if count >= max_players else LobbyStatus.WAITING

    async def create_lobby(self, player_id: str) -> Lobby:
        """Create a lobby with `player_id` as the first member."""
        settings = get_settings()
        max_players = settings.lobby_max_players

        async with self._lock:
            player = await connection_manager.get_player(player_id)
            if player is None:
                msg = "Unknown or disconnected player_id"
                raise LookupError(msg)
            if player.current_room is not None:
                msg = "Player is already in a lobby"
                raise ValueError(msg)

            lobby_id = str(uuid4())
            created = Lobby(
                id=lobby_id,
                players=(player_id,),
                status=self._status_for_count(1, max_players),
            )
            self._lobbies[lobby_id] = created

        await connection_manager.update_player(
            player_id,
            status=PlayerStatus.LOBBY,
            current_room=created.id,
        )
        return created

    async def join_lobby(self, lobby_id: str, player_id: str) -> Lobby:
        """Add a player to a lobby when capacity allows."""
        settings = get_settings()
        max_players = settings.lobby_max_players

        async with self._lock:
            player = await connection_manager.get_player(player_id)
            if player is None:
                msg = "Unknown or disconnected player_id"
                raise LookupError(msg)

            lobby = self._lobbies.get(lobby_id)
            if lobby is None:
                msg = "Lobby not found"
                raise LookupError(msg)

            if player_id in lobby.players:
                return lobby

            if player.current_room is not None and player.current_room != lobby_id:
                msg = "Player is already in another lobby"
                raise ValueError(msg)

            if len(lobby.players) >= max_players:
                msg = "Lobby is full"
                raise ValueError(msg)

            new_players = (*lobby.players, player_id)
            updated = Lobby(
                id=lobby.id,
                players=new_players,
                status=self._status_for_count(len(new_players), max_players),
            )
            self._lobbies[lobby_id] = updated

        await connection_manager.update_player(
            player_id,
            status=PlayerStatus.LOBBY,
            current_room=lobby_id,
        )
        return updated

    async def leave_lobby(self, lobby_id: str, player_id: str) -> None:
        """Remove a player from a lobby; delete the lobby if it becomes empty."""
        max_players = get_settings().lobby_max_players

        async with self._lock:
            lobby = self._lobbies.get(lobby_id)
            if lobby is None:
                msg = "Lobby not found"
                raise LookupError(msg)
            if player_id not in lobby.players:
                msg = "Player is not in this lobby"
                raise ValueError(msg)

            new_players = tuple(p for p in lobby.players if p != player_id)
            if not new_players:
                del self._lobbies[lobby_id]
            else:
                self._lobbies[lobby_id] = Lobby(
                    id=lobby.id,
                    players=new_players,
                    status=self._status_for_count(len(new_players), max_players),
                )

        await connection_manager.update_player(
            player_id,
            status=PlayerStatus.IDLE,
            current_room=None,
        )

    async def get_lobby(self, lobby_id: str) -> Lobby | None:
        """Return a lobby by id, or None if missing."""
        async with self._lock:
            lobby = self._lobbies.get(lobby_id)
            return lobby

    async def remove_player_from_all_lobbies(self, player_id: str) -> None:
        """Remove the player from any lobby (disconnect). Deletes empty lobbies."""
        settings = get_settings()
        max_players = settings.lobby_max_players
        removed_from: str | None = None

        async with self._lock:
            for lid, lobby in list(self._lobbies.items()):
                if player_id not in lobby.players:
                    continue
                removed_from = lid
                new_players = tuple(p for p in lobby.players if p != player_id)
                if not new_players:
                    del self._lobbies[lid]
                else:
                    self._lobbies[lid] = Lobby(
                        id=lobby.id,
                        players=new_players,
                        status=self._status_for_count(len(new_players), max_players),
                    )
                break

        if removed_from is None:
            return
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
        """Clear all lobbies (used by tests)."""
        async with self._lock:
            self._lobbies.clear()


lobby_manager = LobbyManager()
