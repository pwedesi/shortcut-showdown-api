"""In-memory lobby registry with capacity limits."""

from __future__ import annotations

import asyncio
import random
import secrets
import time
from typing import Any

from app.core.config import get_settings
from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.core.websocket_protocol import build_message
from app.services.shortcut_engine import (
    generate_shortcut_sequence,
    publicize_challenges,
)
from app.models.game_room import GameRoom, GameSessionStatus
from app.models.lobby import Lobby, LobbyStatus
from app.models.player import PlayerStatus


_LOBBY_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LOBBY_CODE_LENGTH = 7


def _leader_after_remove(
    lobby: Lobby,
    removed_id: str,
    remaining: tuple[str, ...],
) -> str:
    """If the leader leaves, the next member becomes leader. Else unchanged."""
    if not remaining:
        return lobby.leader_id
    if removed_id == lobby.leader_id:
        return remaining[0]
    return lobby.leader_id


class LobbyManager:
    """Tracks lobbies and keeps `Player` lobby fields in sync when possible."""

    def __init__(self) -> None:
        self._lobbies: dict[str, Lobby] = {}
        self._lock = asyncio.Lock()

    def _status_for_count(self, count: int, max_players: int) -> LobbyStatus:
        return LobbyStatus.FULL if count >= max_players else LobbyStatus.WAITING

    async def _generate_lobby_id(self) -> str:
        while True:
            lobby_id = "".join(
                secrets.choice(_LOBBY_CODE_ALPHABET)
                for _ in range(_LOBBY_CODE_LENGTH)
            )
            if lobby_id in self._lobbies:
                continue
            if await game_room_manager.get_room(lobby_id) is not None:
                continue
            return lobby_id

    async def _public_lobby_payload(self, lobby: Lobby) -> dict[str, Any]:
        players: list[dict[str, str | bool]] = []
        for player_id in lobby.players:
            player = await connection_manager.get_player(player_id)
            display_name = player_id
            is_ready = False
            if player is not None and player.display_name:
                display_name = player.display_name
            if player is not None:
                is_ready = bool(player.is_ready)
            players.append(
                {
                    "player_id": player_id,
                    "display_name": display_name,
                    "is_leader": player_id == lobby.leader_id,
                    "is_ready": is_ready,
                }
            )

        s = get_settings()
        return {
            "id": lobby.id,
            "players": players,
            "status": lobby.status.value,
            "challenge_count": s.challenge_count,
            "round_duration_seconds": s.round_duration_seconds,
            "max_attempts_per_second": s.max_attempts_per_second,
        }

    async def _broadcast_lobby_update(
        self,
        lobby: Lobby,
        *,
        change: str,
        actor_player_id: str | None = None,
    ) -> None:
        await connection_manager.broadcast_to_scope(
            "lobby",
            lobby.id,
            build_message(
                "lobby_updated",
                {
                    "lobby_id": lobby.id,
                    "lobby": await self._public_lobby_payload(lobby),
                    "change": change,
                    "actor_player_id": actor_player_id,
                },
            ),
        )

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

            lobby_id = await self._generate_lobby_id()
            created = Lobby(
                id=lobby_id,
                players=(player_id,),
                status=self._status_for_count(1, max_players),
                leader_id=player_id,
            )
            self._lobbies[lobby_id] = created

        await connection_manager.update_player(
            player_id,
            status=PlayerStatus.LOBBY,
            current_room=created.id,
            is_ready=False,
        )
        await connection_manager.set_subscription(player_id, "lobby", created.id)
        await connection_manager.clear_subscription(player_id, "room")
        await self._broadcast_lobby_update(
            created,
            change="created",
            actor_player_id=player_id,
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
                await connection_manager.set_subscription(player_id, "lobby", lobby.id)
                await connection_manager.clear_subscription(player_id, "room")
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
                leader_id=lobby.leader_id,
            )
            self._lobbies[lobby_id] = updated

        await connection_manager.update_player(
            player_id,
            status=PlayerStatus.LOBBY,
            current_room=lobby_id,
            is_ready=False,
        )
        await connection_manager.set_subscription(player_id, "lobby", lobby_id)
        await connection_manager.clear_subscription(player_id, "room")
        await self._broadcast_lobby_update(
            updated,
            change="joined",
            actor_player_id=player_id,
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
                new_leader = _leader_after_remove(lobby, player_id, new_players)
                self._lobbies[lobby_id] = Lobby(
                    id=lobby.id,
                    players=new_players,
                    status=self._status_for_count(len(new_players), max_players),
                    leader_id=new_leader,
                )

        await connection_manager.update_player(
            player_id,
            status=PlayerStatus.IDLE,
            current_room=None,
            is_ready=False,
        )
        await connection_manager.clear_subscription(player_id, "lobby")
        await connection_manager.clear_subscription(player_id, "room")

        remaining_lobby = await self.get_lobby(lobby_id)
        if remaining_lobby is not None:
            await self._broadcast_lobby_update(
                remaining_lobby,
                change="left",
                actor_player_id=player_id,
            )

    async def get_lobby(self, lobby_id: str) -> Lobby | None:
        """Return a lobby by id, or None if missing."""
        async with self._lock:
            lobby = self._lobbies.get(lobby_id)
            return lobby

    async def start_game(self, lobby_id: str, player_id: str) -> GameRoom:
        """Convert a lobby into a locked game room; players move to in-game."""
        async with self._lock:
            lobby = self._lobbies.pop(lobby_id, None)
            if lobby is None:
                msg = "Lobby not found"
                raise LookupError(msg)
            if player_id not in lobby.players:
                self._lobbies[lobby_id] = lobby
                msg = "Player is not in this lobby"
                raise ValueError(msg)
            if player_id != lobby.leader_id:
                self._lobbies[lobby_id] = lobby
                msg = "Only the room leader can start"
                raise ValueError(msg)

            # generate a shared challenge sequence for the room
            settings = get_settings()
            count = getattr(settings, "challenge_count", 10)
            rng = random.Random(lobby_id)
            challenges = generate_shortcut_sequence(count, rng=rng)
            now = time.time()
            raw_dur = getattr(settings, "round_duration_seconds", 90)
            round_duration = max(1, int(raw_dur))

            player_display_names: dict[str, str] = {}
            for pid in lobby.players:
                player = await connection_manager.get_player(pid)
                if player is not None and player.display_name:
                    player_display_names[pid] = player.display_name
                else:
                    player_display_names[pid] = pid

            room = GameRoom(
                id=lobby_id,
                players=lobby.players,
                game_state={
                    "status": GameSessionStatus.RUNNING.value,
                    "state_version": 1,
                    "round_started_at": now,
                    "round_ends_at": now + round_duration,
                    "objective_count": len(challenges),
                    "challenges": challenges,
                    "roster": list(lobby.players),
                    "player_display_names": player_display_names,
                    "progress": {
                        pid: {
                            "objective_index": 0,
                            "progress_percent": 0.0,
                            "wpm": 0.0,
                            "accuracy": 0.0,
                            "streak": 0,
                            "attempts_total": 0,
                            "attempts_correct": 0,
                            "finished": False,
                            "finished_at": None,
                        }
                        for pid in lobby.players
                    },
                    "rate_limit": {},
                    "attempt_receipts": {},
                    "winner_player_id": None,
                    "draw": False,
                    "end_reason": None,
                    "finished_at": None,
                },
                locked=True,
            )

            try:
                await game_room_manager.register_room(room)
            except Exception:
                self._lobbies[lobby_id] = lobby
                raise

        for pid in room.players:
            await connection_manager.update_player(
                pid,
                status=PlayerStatus.IN_GAME,
                current_room=room.id,
                is_ready=False,
            )
            await connection_manager.set_subscription(pid, "room", room.id)
            await connection_manager.clear_subscription(pid, "lobby")

        from app.core.game_engine import game_engine

        state = await game_engine.get_public_state(room)
        # send the same (public) challenge sequence to every player in the room
        public_challenges = publicize_challenges(room.game_state.get("challenges", []))
        await connection_manager.broadcast_to_scope(
            "room",
            room.id,
            build_message(
                "challenges",
                {
                    "room_id": room.id,
                    "challenges": public_challenges,
                },
            ),
        )
        await connection_manager.broadcast_to_scope(
            "room",
            room.id,
            build_message(
                "game_state_update",
                {
                    "room_id": room.id,
                    "state_version": state.state_version,
                    "game_state": state.model_dump(mode="json"),
                },
            ),
        )
        return room

    async def create_rematch_lobby(
        self,
        player_ids: tuple[str, ...],
        source_room_id: str,
    ) -> Lobby:
        """Create a new lobby for a completed match using the same roster."""
        settings = get_settings()
        max_players = settings.lobby_max_players

        if not player_ids:
            raise ValueError("rematch_roster_empty")
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("rematch_roster_changed")
        if len(player_ids) > max_players:
            raise ValueError("rematch_roster_changed")

        async with self._lock:
            validated_players: list[str] = []
            for player_id in player_ids:
                player = await connection_manager.get_player(player_id)
                if player is None:
                    raise ValueError("rematch_roster_changed")
                if player.current_room != source_room_id:
                    raise ValueError("rematch_roster_changed")
                validated_players.append(player_id)

            lobby_id = await self._generate_lobby_id()
            created = Lobby(
                id=lobby_id,
                players=tuple(validated_players),
                status=self._status_for_count(len(validated_players), max_players),
                leader_id=validated_players[0],
            )
            self._lobbies[lobby_id] = created

        updated_players: list[str] = []
        try:
            for player_id in validated_players:
                updated = await connection_manager.update_player(
                    player_id,
                    status=PlayerStatus.LOBBY,
                    current_room=created.id,
                )
                if updated is None:
                    raise ValueError("rematch_roster_changed")
                updated_players.append(player_id)
                await connection_manager.set_subscription(
                    player_id,
                    "lobby",
                    created.id,
                )
                await connection_manager.clear_subscription(player_id, "room")
        except Exception:
            async with self._lock:
                self._lobbies.pop(created.id, None)
            for player_id in updated_players:
                await connection_manager.update_player(
                    player_id,
                    status=PlayerStatus.IN_GAME,
                    current_room=source_room_id,
                )
                await connection_manager.set_subscription(
                    player_id,
                    "room",
                    source_room_id,
                )
                await connection_manager.clear_subscription(player_id, "lobby")
            raise

        await self._broadcast_lobby_update(created, change="rematch_created")

        return created

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
                    new_leader = _leader_after_remove(lobby, player_id, new_players)
                    self._lobbies[lid] = Lobby(
                        id=lobby.id,
                        players=new_players,
                        status=self._status_for_count(len(new_players), max_players),
                        leader_id=new_leader,
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
        await connection_manager.clear_subscription(player_id, "lobby")
        await connection_manager.clear_subscription(player_id, "room")

    async def reset(self) -> None:
        """Clear all lobbies (used by tests)."""
        async with self._lock:
            self._lobbies.clear()


lobby_manager = LobbyManager()
