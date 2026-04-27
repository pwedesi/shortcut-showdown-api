"""Lobby model for pre-match player grouping."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LobbyStatus(StrEnum):
    WAITING = "waiting"
    FULL = "full"


class Lobby(BaseModel):
    """A waiting room before a match."""

    model_config = ConfigDict(frozen=True)

    id: str
    players: tuple[str, ...] = Field(default_factory=tuple)
    status: LobbyStatus = LobbyStatus.WAITING
    leader_id: str


class LobbyPlayerView(BaseModel):
    """A lobby roster entry (creator/leader is flagged)."""

    player_id: str
    display_name: str
    is_leader: bool
    is_ready: bool


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
                        "is_leader": True,
                        "is_ready": True,
                    },
                    {
                        "player_id": "player-b",
                        "display_name": "MAVERICK",
                        "is_leader": False,
                        "is_ready": False,
                    },
                ],
                "status": "waiting",
                "challenge_count": 10,
                "round_duration_seconds": 90,
                "max_attempts_per_second": 8,
            }
        }
    )

    id: str
    players: list[LobbyPlayerView] = Field(default_factory=list)
    status: LobbyStatus
    challenge_count: int
    round_duration_seconds: int
    max_attempts_per_second: int
