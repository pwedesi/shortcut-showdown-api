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
