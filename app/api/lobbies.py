"""REST endpoints for lobby create, join, leave, and inspect."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.game_rooms import game_room_to_response
from app.core.lobby_manager import lobby_manager
from app.models.lobby import Lobby

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


class PlayerIdBody(BaseModel):
    """Request body carrying a single active player id."""

    player_id: str


def _lobby_to_response(lobby: Lobby) -> dict[str, object]:
    return {
        "id": lobby.id,
        "players": list(lobby.players),
        "status": lobby.status.value,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lobby(body: PlayerIdBody) -> dict[str, object]:
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
    return _lobby_to_response(lobby)


@router.post("/{lobby_id}/join")
async def join_lobby(lobby_id: str, body: PlayerIdBody) -> dict[str, object]:
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
    return _lobby_to_response(lobby)


@router.post("/{lobby_id}/start")
async def start_game(lobby_id: str, body: PlayerIdBody) -> dict[str, object]:
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
    return game_room_to_response(room)


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


@router.get("/{lobby_id}")
async def get_lobby(lobby_id: str) -> dict[str, object]:
    """Return lobby details including the ordered player list."""
    lobby = await lobby_manager.get_lobby(lobby_id)
    if lobby is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lobby not found",
        )
    return _lobby_to_response(lobby)
