"""Lobby model for pre-match player grouping."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.player import PlayerIdentityView


class LobbyStatus(StrEnum):
    WAITING = "waiting"
    FULL = "full"


class Lobby(BaseModel):
    """A waiting room before a match."""

    model_config = ConfigDict(frozen=True)

    id: str
    players: tuple[str, ...] = Field(default_factory=tuple)
    status: LobbyStatus = LobbyStatus.WAITING


class LobbyView(BaseModel):
    """Public lobby payload with resolved player identities."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "K7M4QZ1",
                "players": [
                    {
                        "player_id": "player-a",
                        "display_name": "OPERATOR_01",
                    },
                    {
                        "player_id": "player-b",
                        "display_name": "MAVERICK",
                    },
                ],
                "status": "waiting",
            }
        }
    )

    id: str
    players: list[PlayerIdentityView] = Field(default_factory=list)
    status: LobbyStatus
