"""Player session model tied to WebSocket connections."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PlayerStatus(StrEnum):
    IDLE = "idle"
    LOBBY = "lobby"
    IN_GAME = "in-game"


class Player(BaseModel):
    """In-memory player snapshot for an active connection."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str = ""
    status: PlayerStatus = PlayerStatus.IDLE
    current_room: str | None = None
