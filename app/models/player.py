"""Player session model tied to WebSocket connections."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

DISPLAY_NAME_MAX_LENGTH = 24
_DISPLAY_NAME_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9 _-]+$")


def normalize_display_name(display_name: str) -> str:
    """Normalize and validate a callsign for server-side storage."""
    normalized = display_name.strip()
    if not normalized:
        msg = "display_name_empty"
        raise ValueError(msg)
    if len(normalized) > DISPLAY_NAME_MAX_LENGTH:
        msg = "display_name_too_long"
        raise ValueError(msg)
    if not _DISPLAY_NAME_ALLOWED_PATTERN.fullmatch(normalized):
        msg = "display_name_invalid_characters"
        raise ValueError(msg)
    return normalized


class PlayerStatus(StrEnum):
    IDLE = "idle"
    LOBBY = "lobby"
    IN_GAME = "in-game"


class UpdateDisplayNameRequest(BaseModel):
    """Write payload for setting a player's callsign."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "OPERATOR_01",
            }
        }
    )

    display_name: str = Field()


class PlayerIdentityView(BaseModel):
    """Public identity payload used by lobby and player endpoints."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player_id": "9e808624-7b6d-4d0f-a0f9-4afc06de2d54",
                "display_name": "OPERATOR_01",
            }
        }
    )

    player_id: str
    display_name: str


class Player(BaseModel):
    """In-memory player snapshot for an active connection."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str = ""
    status: PlayerStatus = PlayerStatus.IDLE
    current_room: str | None = None
