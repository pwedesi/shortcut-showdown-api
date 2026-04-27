"""REST endpoints for player identity updates."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.connection_manager import connection_manager
from app.models.player import (
    PlayerIdentityView,
    UpdatePlayerRequest,
    normalize_display_name,
)

router = APIRouter(prefix="/players", tags=["players"])


@router.patch("/{player_id}", response_model=PlayerIdentityView)
async def update_player_display_name(
    player_id: str,
    body: UpdatePlayerRequest,
) -> PlayerIdentityView:
    """Set or update a player's callsign by active player id."""
    player = await connection_manager.get_player(player_id)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="player_not_found",
        )

    update_fields: dict[str, object] = {}

    if body.display_name is not None:
        try:
            display_name = normalize_display_name(body.display_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        update_fields["display_name"] = display_name

    if body.is_ready is not None:
        update_fields["is_ready"] = bool(body.is_ready)

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="empty_patch",
        )

    updated = await connection_manager.update_player(
        player_id,
        **update_fields,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="player_not_found",
        )

    return PlayerIdentityView(
        player_id=updated.id,
        display_name=updated.display_name,
        is_ready=updated.is_ready,
    )
