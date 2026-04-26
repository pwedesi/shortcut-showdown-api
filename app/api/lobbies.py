"""REST endpoints for lobby create, join, leave, and inspect."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.game_rooms import game_room_to_response
from app.core.config import get_settings
from app.core.connection_manager import connection_manager
from app.core.lobby_manager import lobby_manager
from app.models.game_room import GameRoomView
from app.models.lobby import Lobby, LobbyPlayerView, LobbyView

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


class PlayerIdBody(BaseModel):
    """Request body carrying a single active player id."""

    player_id: str


async def _lobby_to_response(lobby: Lobby) -> LobbyView:
    players: list[LobbyPlayerView] = []
    for player_id in lobby.players:
        player = await connection_manager.get_player(player_id)
        display_name = player_id
        if player is not None and player.display_name:
            display_name = player.display_name
        players.append(
            LobbyPlayerView(
                player_id=player_id,
                display_name=display_name,
                is_leader=player_id == lobby.leader_id,
            )
        )

    settings = get_settings()
    return LobbyView(
        id=lobby.id,
        players=players,
        status=lobby.status,
        challenge_count=settings.challenge_count,
        round_duration_seconds=settings.round_duration_seconds,
        max_attempts_per_second=settings.max_attempts_per_second,
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


@router.post("/{lobby_id}/join", response_model=LobbyView)
async def join_lobby(lobby_id: str, body: PlayerIdBody) -> LobbyView:
    """Join an existing lobby when it is not full."""
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
