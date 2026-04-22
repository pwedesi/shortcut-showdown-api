"""REST endpoints for active game rooms."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, status

from app.core.game_engine import game_engine
from app.core.game_room_manager import game_room_manager
from app.models.game_room import AttemptRequest, AttemptResponse, GameRoom, GameRoomView

router = APIRouter(prefix="/game-rooms", tags=["game-rooms"])


async def game_room_to_response(room: GameRoom) -> GameRoomView:
    """Serialize a game room with authoritative server-owned state."""
    state = await game_engine.get_public_state(room)
    return GameRoomView(
        id=room.id,
        players=list(room.players),
        game_state=state,
        locked=room.locked,
    )


@router.get("/{room_id}", response_model=GameRoomView)
async def get_game_room(room_id: str) -> GameRoomView:
    """Return game room details including players and game state."""
    room = await game_room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )
    return await game_room_to_response(room)


@router.post("/{room_id}/attempts", response_model=AttemptResponse)
async def submit_attempt(
    room_id: str,
    body: AttemptRequest = Body(
        ...,
        openapi_examples={
            "correctAttempt": {
                "summary": "Accepted attempt",
                "value": {
                    "player_id": "player-a",
                    "objective_index": 3,
                    "keys": ["ctrl", "s"],
                    "attempt_id": "attempt-0003",
                },
            },
            "invalidIndex": {
                "summary": "Rejected out-of-order attempt",
                "value": {
                    "player_id": "player-a",
                    "objective_index": 8,
                    "keys": ["ctrl", "s"],
                    "attempt_id": "attempt-0004",
                },
            },
        },
    ),
) -> AttemptResponse:
    """Submit an authoritative player attempt for the room's active round."""
    room = await game_room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )

    try:
        return await game_engine.submit_attempt(
            room_id=room_id,
            player_id=body.player_id,
            objective_index=body.objective_index,
            keys=body.keys,
            attempt_id=body.attempt_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
