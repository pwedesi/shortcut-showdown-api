"""REST endpoints for lobby create, join, leave, and inspect."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.game_rooms import game_room_to_response
from app.core.config import get_settings
from app.core.connection_manager import connection_manager

logger = logging.getLogger(__name__)
from app.core.lobby_manager import lobby_manager
from app.models.game_room import GameRoomView
from app.models.lobby import Lobby, LobbyPlayerView, LobbyView

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


class PlayerIdBody(BaseModel):
    """Request body carrying a single active player id."""

    player_id: str


class SetMaxPlayersBody(BaseModel):
    """Request body for setting max players in a lobby."""

    player_id: str
    max_players: int


class SetChallengeCountBody(BaseModel):
    """Request body for setting the number of challenges (papers) in a lobby."""

    player_id: str
    challenge_count: int


class SetRoundDurationBody(BaseModel):
    """Request body for setting the round duration in a lobby."""

    player_id: str
    round_duration_seconds: int


async def _lobby_to_response(lobby: Lobby) -> LobbyView:
    players: list[LobbyPlayerView] = []
    for player_id in lobby.players:
        player = await connection_manager.get_player(player_id)
        display_name = player_id
        is_ready = False
        if player is not None and player.display_name:
            display_name = player.display_name
        if player is not None:
            is_ready = player.is_ready
        players.append(
            LobbyPlayerView(
                player_id=player_id,
                display_name=display_name,
                is_leader=player_id == lobby.leader_id,
                is_ready=is_ready,
            )
        )

    settings = get_settings()
    return LobbyView(
        id=lobby.id,
        players=players,
        status=lobby.status,
        challenge_count=lobby.challenge_count,
        round_duration_seconds=lobby.round_duration_seconds,
        max_attempts_per_second=settings.max_attempts_per_second,
        locked=lobby.locked,
        max_players=lobby.max_players,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LobbyView)
async def create_lobby(body: PlayerIdBody) -> LobbyView:
    """Create a new lobby; the player becomes the host and first member."""
    try:
        lobby = await lobby_manager.create_lobby(body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/quick-play", response_model=LobbyView)
async def quick_play(body: PlayerIdBody) -> LobbyView:
    """Auto-join a random available unlocked lobby or create a new one."""
    try:
        lobby = await lobby_manager.quick_play(body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/join", response_model=LobbyView)
async def join_lobby(lobby_id: str, body: PlayerIdBody) -> LobbyView:
    """Join an existing lobby when it is not full. (Locked status is hidden from quick-play but directly joinable)."""
    try:
        lobby = await lobby_manager.join_lobby(lobby_id, body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/start")
async def start_game(lobby_id: str, body: PlayerIdBody) -> GameRoomView:
    """Start a match: lobby becomes a locked game room; players enter gameplay."""
    try:
        room = await lobby_manager.start_game(lobby_id, body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return await game_room_to_response(room)


@router.post("/{lobby_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_lobby(lobby_id: str, body: PlayerIdBody) -> None:
    """Leave a lobby; the lobby is removed when the last player leaves."""
    try:
        await lobby_manager.leave_lobby(lobby_id, body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/{lobby_id}", response_model=LobbyView)
async def get_lobby(lobby_id: str) -> LobbyView:
    """Return lobby details including the ordered player list."""
    lobby = await lobby_manager.get_lobby(lobby_id)
    if lobby is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lobby not found",
        )
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/lock", response_model=LobbyView)
async def lock_lobby(lobby_id: str, body: PlayerIdBody) -> LobbyView:
    """Host locks the lobby to prevent new players from joining (quickplay hidden)."""
    try:
        lobby = await lobby_manager.lock_lobby(lobby_id, body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/unlock", response_model=LobbyView)
async def unlock_lobby(lobby_id: str, body: PlayerIdBody) -> LobbyView:
    """Host unlocks the lobby to allow new players from quickplay."""
    try:
        lobby = await lobby_manager.unlock_lobby(lobby_id, body.player_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/set-max-players", response_model=LobbyView)
async def set_max_players(lobby_id: str, body: SetMaxPlayersBody) -> LobbyView:
    """Host sets the maximum number of players for the lobby."""
    try:
        lobby = await lobby_manager.set_max_players(
            lobby_id, body.player_id, body.max_players
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/set-challenge-count", response_model=LobbyView)
async def set_challenge_count(lobby_id: str, body: SetChallengeCountBody) -> LobbyView:
    """Host sets the number of challenges (papers) for the lobby."""
    try:
        lobby = await lobby_manager.set_challenge_count(
            lobby_id, body.player_id, body.challenge_count
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)


@router.post("/{lobby_id}/set-round-duration", response_model=LobbyView)
async def set_round_duration(lobby_id: str, body: SetRoundDurationBody) -> LobbyView:
    """Host sets the maximum duration for the match in the lobby."""
    try:
        lobby = await lobby_manager.set_round_duration(
            lobby_id, body.player_id, body.round_duration_seconds
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return await _lobby_to_response(lobby)
