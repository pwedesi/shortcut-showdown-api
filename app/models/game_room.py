"""Game room model for an active match session."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GameRoom(BaseModel):
    """An isolated gameplay session created from a lobby."""

    model_config = ConfigDict(frozen=True)

    id: str
    players: tuple[str, ...] = Field(default_factory=tuple)
    game_state: dict[str, Any] = Field(default_factory=dict)
    locked: bool = True
