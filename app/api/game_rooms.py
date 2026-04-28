"""REST endpoints for active game rooms."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, status
from pydantic import BaseModel

from app.core.connection_manager import connection_manager
from app.core.game_engine import game_engine
from app.core.game_room_manager import game_room_manager
from app.core.lobby_manager import lobby_manager
from app.core.websocket_protocol import build_message
from app.models.game_room import (
    AttemptRequest,
    AttemptResponse,
    GameRoom,
    GameRoomView,
    MatchResultsView,
)

router = APIRouter(prefix="/game-rooms", tags=["game-rooms"])


class RematchRequest(BaseModel):
    """Request body for creating a rematch lobby."""

    player_id: str


class RematchResponse(BaseModel):
    """Response body for a successful rematch creation."""

    room_id: str
    next_lobby_id: str


class RematchAcceptanceResponse(BaseModel):
    """Response when a player accepts/declines rematch."""

    room_id: str
    player_id: str
    accepted: bool
    all_accepted: bool
    pending_players: list[str]


async def game_room_to_response(room: GameRoom) -> GameRoomView:
    """Serialize a game room with authoritative server-owned state."""
    state = await game_engine.get_public_state(room)
    return GameRoomView(
        id=room.id,
        players=list(room.players),
        game_state=state,
        locked=room.locked,
    )


def _room_roster(room: GameRoom) -> tuple[str, ...]:
    roster = room.game_state.get("roster")
    if isinstance(roster, (list, tuple)):
        return tuple(str(player_id) for player_id in roster if str(player_id))
    return room.players


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


@router.get("/{room_id}/results", response_model=MatchResultsView)
async def get_match_results(
    room_id: str,
    player_id: str | None = Query(
        default=None,
        description="Active player id to echo for client-side self highlighting.",
    ),
) -> MatchResultsView:
    """Return the final leaderboard for a finished match."""
    try:
        return await game_engine.get_match_results(
            room_id,
            viewer_player_id=player_id,
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


@router.post(
    "/{room_id}/rematch/accept",
    status_code=status.HTTP_200_OK,
    response_model=RematchAcceptanceResponse,
)
async def accept_rematch(room_id: str, body: RematchRequest) -> RematchAcceptanceResponse:
    """Player accepts rematch; auto-creates lobby if all accept."""
    room = await game_room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )

    state = await game_engine.ensure_room_state(room_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )
    if not state.finished:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="match_not_finished",
        )
    if body.player_id not in room.players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="player_not_in_match",
        )

    # Initialize rematch acceptances if not present
    acceptances = room.game_state.get("rematch_acceptances", {})
    if not isinstance(acceptances, dict):
        acceptances = {}
    
    acceptances[body.player_id] = True
    pending = [p for p in room.players if p not in acceptances or not acceptances[p]]
    
    # Update room with acceptances
    new_game_state = dict(room.game_state)
    new_game_state["rematch_acceptances"] = acceptances
    new_room = GameRoom(
        id=room.id,
        players=room.players,
        game_state=new_game_state,
        locked=room.locked,
    )
    await game_room_manager.register_room(new_room)
    
    # Check if we can start
    active_players = []
    for pid in room.players:
        p = await connection_manager.get_player(pid)
        if p is not None:
            active_players.append(pid)
    
    pending = [pid for pid in active_players if pid not in acceptances]
    all_accepted_ids = [pid for pid, val in acceptances.items() if val is True]
    
    # Broadcast acceptance update to everyone in the room
    await connection_manager.broadcast_to_scope(
        "room",
        room_id,
        build_message(
            "rematch_acceptance_update",
            {
                "room_id": room_id,
                "acceptances": acceptances,
                "pending_players": pending,
            },
        ),
    )
    
    if not pending and all_accepted_ids:
        # Everyone active has decided, and at least one person accepted
        try:
            lobby = await lobby_manager.create_rematch_lobby(tuple(all_accepted_ids), room_id)
            await connection_manager.broadcast_to_scope(
                "room",
                room_id,
                build_message(
                    "rematch_ready",
                    {
                        "room_id": room_id,
                        "next_lobby_id": lobby.id,
                    },
                ),
            )
            return RematchAcceptanceResponse(
                room_id=room_id,
                player_id=body.player_id,
                accepted=True,
                all_accepted=True,
                pending_players=[],
            )
        except ValueError as exc:
            # If creation fails (e.g. players moved), just return status
            logger.warning(f"Rematch lobby creation failed: {exc}")

    return RematchAcceptanceResponse(
        room_id=room_id,
        player_id=body.player_id,
        accepted=True,
        all_accepted=not pending,
        pending_players=pending,
    )


@router.post(
    "/{room_id}/rematch/decline",
    status_code=status.HTTP_200_OK,
    response_model=RematchAcceptanceResponse,
)
async def decline_rematch(room_id: str, body: RematchRequest) -> RematchAcceptanceResponse:
    """Player declines rematch."""
    room = await game_room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )

    state = await game_engine.ensure_room_state(room_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )
    if body.player_id not in room.players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="player_not_in_match",
        )

    # Initialize rematch acceptances if not present
    acceptances = room.game_state.get("rematch_acceptances", {})
    if not isinstance(acceptances, dict):
        acceptances = {}
    
    acceptances[body.player_id] = False
    pending = [p for p in room.players if p not in acceptances or acceptances[p] is None]
    
    # Update room with decline
    new_game_state = dict(room.game_state)
    new_game_state["rematch_acceptances"] = acceptances
    new_room = GameRoom(
        id=room.id,
        players=room.players,
        game_state=new_game_state,
        locked=room.locked,
    )
    await game_room_manager.register_room(new_room)
    
    # Check if we can start
    active_players = []
    for pid in room.players:
        p = await connection_manager.get_player(pid)
        if p is not None:
            active_players.append(pid)
            
    pending = [pid for pid in active_players if pid not in acceptances]
    all_accepted_ids = [pid for pid, val in acceptances.items() if val is True]

    if not pending and all_accepted_ids:
        try:
            lobby = await lobby_manager.create_rematch_lobby(tuple(all_accepted_ids), room_id)
            await connection_manager.broadcast_to_scope(
                "room",
                room_id,
                build_message(
                    "rematch_ready",
                    {
                        "room_id": room_id,
                        "next_lobby_id": lobby.id,
                    },
                ),
            )
        except ValueError:
            pass

    # Broadcast decline notification
    await connection_manager.broadcast_to_scope(
        "room",
        room_id,
        build_message(
            "rematch_declined",
            {
                "room_id": room_id,
                "player_id": body.player_id,
            },
        ),
    )
    
    # Also send an update for pending players
    await connection_manager.broadcast_to_scope(
        "room",
        room_id,
        build_message(
            "rematch_acceptance_update",
            {
                "room_id": room_id,
                "acceptances": acceptances,
                "pending_players": pending,
            },
        ),
    )
    
    return RematchAcceptanceResponse(
        room_id=room_id,
        player_id=body.player_id,
        accepted=False,
        all_accepted=not pending and bool(all_accepted_ids),
        pending_players=pending,
    )


@router.post(
    "/{room_id}/rematch",
    status_code=status.HTTP_201_CREATED,
    response_model=RematchResponse,
)
async def create_rematch(room_id: str, body: RematchRequest) -> RematchResponse:
    """Create a fresh lobby for the same finished roster (legacy endpoint)."""
    room = await game_room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )

    state = await game_engine.ensure_room_state(room_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game room not found",
        )
    if not state.finished:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="match_not_finished",
        )
    if body.player_id not in room.players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="player_not_in_match",
        )

    roster = _room_roster(room)
    if tuple(room.players) != roster:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="rematch_roster_changed",
        )

    try:
        lobby = await lobby_manager.create_rematch_lobby(roster, room_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return RematchResponse(room_id=room_id, next_lobby_id=lobby.id)


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
                    "keys": ["ctrl", "c"],
                    "attempt_id": "attempt-0003",
                },
            },
            "invalidIndex": {
                "summary": "Rejected out-of-order attempt",
                "value": {
                    "player_id": "player-a",
                    "objective_index": 8,
                    "keys": ["ctrl", "c"],
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
