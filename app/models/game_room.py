"""Game room model for an active match session."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GameSessionStatus(StrEnum):
    """Authoritative round states controlled by the server."""

    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"


class GameEndReason(StrEnum):
    """Reasons why a round can end."""

    TIME = "time"
    GOAL = "goal"
    FORFEIT = "forfeit"


class PublicChallenge(BaseModel):
    """Client-safe challenge payload (answer keys are omitted)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "index": 0,
                "prompt": "Copy selected text",
            }
        }
    )

    index: int = 0
    prompt: str


class PlayerGameProgress(BaseModel):
    """Per-player telemetry computed server-side."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "objective_index": 3,
                "progress_percent": 30.0,
                "wpm": 46.2,
                "accuracy": 88.9,
                "streak": 2,
                "attempts_total": 9,
                "attempts_correct": 8,
                "finished": False,
                "finished_at": None,
            }
        }
    )

    objective_index: int = 0
    progress_percent: float = 0.0
    wpm: float = 0.0
    accuracy: float = 0.0
    streak: int = 0
    attempts_total: int = 0
    attempts_correct: int = 0
    finished: bool = False
    finished_at: float | None = None


class GameStateView(BaseModel):
    """Authoritative public game state exposed to all clients.

    Tie-breaking order for timeout/forfeit outcomes is deterministic:
    higher objective_index, then higher accuracy, then higher wpm,
    then lexicographically smaller player_id.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "running",
                "state_version": 7,
                "server_time": 1713806420.45,
                "round_started_at": 1713806360.12,
                "round_ends_at": 1713806450.12,
                "objective_count": 10,
                "challenges": [
                    {"index": 0, "prompt": "Copy selected text"},
                    {"index": 1, "prompt": "Paste"},
                ],
                "players": {
                    "player-a": {
                        "objective_index": 3,
                        "progress_percent": 30.0,
                        "wpm": 46.2,
                        "accuracy": 88.9,
                        "streak": 2,
                        "attempts_total": 9,
                        "attempts_correct": 8,
                        "finished": False,
                        "finished_at": None,
                    },
                    "player-b": {
                        "objective_index": 2,
                        "progress_percent": 20.0,
                        "wpm": 33.1,
                        "accuracy": 75.0,
                        "streak": 1,
                        "attempts_total": 8,
                        "attempts_correct": 6,
                        "finished": False,
                        "finished_at": None,
                    },
                },
                "finished": False,
                "winner_player_id": None,
                "draw": False,
                "end_reason": None,
                "finished_at": None,
            }
        }
    )

    status: GameSessionStatus
    state_version: int
    server_time: float
    round_started_at: float
    round_ends_at: float
    objective_count: int
    challenges: list[PublicChallenge] = Field(default_factory=list)
    players: dict[str, PlayerGameProgress] = Field(default_factory=dict)
    finished: bool = False
    winner_player_id: str | None = None
    draw: bool = False
    end_reason: GameEndReason | None = None
    finished_at: float | None = None


class GameRoomView(BaseModel):
    """Public response for game room read endpoints."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "6f7f7f8f-47c2-4f0f-9ea1-063177f57ed0",
                "players": ["player-a", "player-b"],
                "locked": True,
                "game_state": {
                    "status": "running",
                    "state_version": 7,
                    "server_time": 1713806420.45,
                    "round_started_at": 1713806360.12,
                    "round_ends_at": 1713806450.12,
                    "objective_count": 10,
                    "challenges": [
                        {"index": 0, "prompt": "Copy selected text"},
                        {"index": 1, "prompt": "Paste"},
                    ],
                    "players": {
                        "player-a": {
                            "objective_index": 3,
                            "progress_percent": 30.0,
                            "wpm": 46.2,
                            "accuracy": 88.9,
                            "streak": 2,
                            "attempts_total": 9,
                            "attempts_correct": 8,
                            "finished": False,
                            "finished_at": None,
                        },
                        "player-b": {
                            "objective_index": 2,
                            "progress_percent": 20.0,
                            "wpm": 33.1,
                            "accuracy": 75.0,
                            "streak": 1,
                            "attempts_total": 8,
                            "attempts_correct": 6,
                            "finished": False,
                            "finished_at": None,
                        },
                    },
                    "finished": False,
                    "winner_player_id": None,
                    "draw": False,
                    "end_reason": None,
                    "finished_at": None,
                },
            }
        }
    )

    id: str
    players: list[str] = Field(default_factory=list)
    game_state: GameStateView
    locked: bool = True


class MatchPlacementView(BaseModel):
    """Final podium entry for a completed match."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player_id": "player-a",
                "display_name": "OPERATOR_01",
                "place": 1,
                "objective_index": 10,
                "progress_percent": 100.0,
                "wpm": 52.4,
                "accuracy": 95.0,
                "streak": 4,
                "attempts_total": 11,
                "attempts_correct": 10,
                "finished": True,
                "finished_at": 1713806452.5,
            }
        }
    )

    player_id: str
    display_name: str
    place: int
    objective_index: int
    progress_percent: float
    wpm: float
    accuracy: float
    streak: int
    attempts_total: int
    attempts_correct: int
    finished: bool
    finished_at: float | None = None


class MatchResultsView(BaseModel):
    """Final results payload for a finished match."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "room_id": "6f7f7f8f-47c2-4f0f-9ea1-063177f57ed0",
                "you_player_id": "player-a",
                "placements": [
                    {
                        "player_id": "player-a",
                        "display_name": "OPERATOR_01",
                        "place": 1,
                        "objective_index": 10,
                        "progress_percent": 100.0,
                        "wpm": 52.4,
                        "accuracy": 95.0,
                        "streak": 4,
                        "attempts_total": 11,
                        "attempts_correct": 10,
                        "finished": True,
                        "finished_at": 1713806452.5,
                    },
                    {
                        "player_id": "player-b",
                        "display_name": "MAVERICK",
                        "place": 2,
                        "objective_index": 7,
                        "progress_percent": 70.0,
                        "wpm": 38.1,
                        "accuracy": 88.9,
                        "streak": 2,
                        "attempts_total": 9,
                        "attempts_correct": 8,
                        "finished": False,
                        "finished_at": None,
                    },
                ],
                "winner_player_id": "player-a",
                "draw": False,
                "end_reason": "goal",
                "ended_at": 1713806452.5,
                "finished": True,
            }
        }
    )

    room_id: str
    you_player_id: str | None = None
    placements: list[MatchPlacementView] = Field(default_factory=list)
    winner_player_id: str | None = None
    draw: bool = False
    end_reason: GameEndReason | None = None
    ended_at: float | None = None
    finished: bool = True


class AttemptRequest(BaseModel):
    """Authoritative write payload for shortcut attempts."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "player_id": "player-a",
                "objective_index": 3,
                "keys": ["ctrl", "s"],
                "attempt_id": "attempt-0003",
            }
        }
    )

    player_id: str
    objective_index: int
    keys: list[str] = Field(default_factory=list)
    attempt_id: str | None = None


class AttemptResponse(BaseModel):
    """Attempt result and latest authoritative room snapshot."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "room_id": "6f7f7f8f-47c2-4f0f-9ea1-063177f57ed0",
                "player_id": "player-a",
                "accepted": True,
                "reason": None,
                "correct": True,
                "objective_index": 4,
                "state_version": 8,
                "game_state": {
                    "status": "running",
                    "state_version": 8,
                    "server_time": 1713806421.12,
                    "round_started_at": 1713806360.12,
                    "round_ends_at": 1713806450.12,
                    "objective_count": 10,
                    "challenges": [
                        {"index": 0, "prompt": "Copy selected text"},
                        {"index": 1, "prompt": "Paste"},
                    ],
                    "players": {
                        "player-a": {
                            "objective_index": 4,
                            "progress_percent": 40.0,
                            "wpm": 48.1,
                            "accuracy": 90.0,
                            "streak": 3,
                            "attempts_total": 10,
                            "attempts_correct": 9,
                            "finished": False,
                            "finished_at": None,
                        },
                        "player-b": {
                            "objective_index": 2,
                            "progress_percent": 20.0,
                            "wpm": 33.1,
                            "accuracy": 75.0,
                            "streak": 1,
                            "attempts_total": 8,
                            "attempts_correct": 6,
                            "finished": False,
                            "finished_at": None,
                        },
                    },
                    "finished": False,
                    "winner_player_id": None,
                    "draw": False,
                    "end_reason": None,
                    "finished_at": None,
                },
            }
        }
    )

    room_id: str
    player_id: str
    accepted: bool
    reason: str | None = None
    correct: bool | None = None
    objective_index: int = 0
    state_version: int = 0
    game_state: GameStateView


class GameRoom(BaseModel):
    """An isolated gameplay session created from a lobby."""

    model_config = ConfigDict(frozen=True)

    id: str
    players: tuple[str, ...] = Field(default_factory=tuple)
    game_state: dict[str, Any] = Field(default_factory=dict)
    locked: bool = True
