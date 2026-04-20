"""REST endpoints for active game rooms."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.game_room_manager import game_room_manager
from app.models.game_room import GameRoom
from app.services.shortcut_engine import publicize_challenges

router = APIRouter(prefix="/game-rooms", tags=["game-rooms"])


def game_room_to_response(room: GameRoom) -> dict[str, object]:
    """Serialize a game room for JSON responses (hide internal answers)."""
    public_state: dict[str, object] = {}
    if "challenges" in room.game_state:
        public_state["challenges"] = publicize_challenges(room.game_state["challenges"])
    return {
        "id": room.id,
        "players": list(room.players),
        "game_state": public_state,
        "locked": room.locked,
    }


@router.get("/{room_id}")
async def get_game_room(room_id: str) -> dict[str, object]:
    """Return game room details including players and game state."""
    room = await game_room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )
    return game_room_to_response(room)
