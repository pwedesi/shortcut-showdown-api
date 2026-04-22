"""Authoritative gameplay engine for room state, attempts, and outcomes."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import get_settings
from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.models.game_room import (
    AttemptResponse,
    GameEndReason,
    GameRoom,
    GameSessionStatus,
    GameStateView,
    PlayerGameProgress,
)
from app.services.shortcut_engine import publicize_challenges


class GameEngine:
    """Server-owned state machine for multiplayer gameplay."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @staticmethod
    def _normalize_keys(keys: list[str]) -> tuple[str, ...]:
        normalized = {str(k).strip().lower() for k in keys if str(k).strip()}
        return tuple(sorted(normalized))

    @staticmethod
    def _initial_progress() -> dict[str, Any]:
        return {
            "objective_index": 0,
            "progress_percent": 0.0,
            "wpm": 0.0,
            "accuracy": 0.0,
            "streak": 0,
            "attempts_total": 0,
            "attempts_correct": 0,
            "finished": False,
            "finished_at": None,
        }

    @staticmethod
    def _increment_state_version(gs: dict[str, Any]) -> None:
        gs["state_version"] = int(gs.get("state_version", 0)) + 1

    @staticmethod
    def _as_status(value: Any) -> GameSessionStatus:
        try:
            return GameSessionStatus(str(value))
        except ValueError:
            return GameSessionStatus.RUNNING

    @staticmethod
    def _as_end_reason(value: Any) -> GameEndReason | None:
        if value is None:
            return None
        try:
            return GameEndReason(str(value))
        except ValueError:
            return None

    def _ensure_player_progress(
        self,
        gs: dict[str, Any],
        player_id: str,
    ) -> dict[str, Any]:
        progress = gs.setdefault("progress", {})
        data = progress.setdefault(player_id, self._initial_progress())
        for key, default in self._initial_progress().items():
            data.setdefault(key, default)
        return data

    @staticmethod
    def _challenge_count(gs: dict[str, Any]) -> int:
        challenges = gs.get("challenges", [])
        count = len(challenges) if isinstance(challenges, list) else 0
        gs["objective_count"] = count
        return count

    def _recompute_metrics(
        self,
        player_progress: dict[str, Any],
        challenge_count: int,
        round_started_at: float,
        now: float,
    ) -> None:
        objective_index = max(0, int(player_progress.get("objective_index", 0)))
        attempts_total = max(0, int(player_progress.get("attempts_total", 0)))
        attempts_correct = max(0, int(player_progress.get("attempts_correct", 0)))

        player_progress["objective_index"] = objective_index
        player_progress["attempts_total"] = attempts_total
        player_progress["attempts_correct"] = attempts_correct

        if challenge_count <= 0:
            player_progress["progress_percent"] = 100.0
        else:
            player_progress["progress_percent"] = min(
                100.0,
                (objective_index / challenge_count) * 100.0,
            )

        if attempts_total <= 0:
            player_progress["accuracy"] = 0.0
        else:
            player_progress["accuracy"] = (attempts_correct / attempts_total) * 100.0

        elapsed = max(0.0, now - round_started_at)
        if elapsed <= 0:
            player_progress["wpm"] = 0.0
        else:
            player_progress["wpm"] = objective_index / (elapsed / 60.0)

        if challenge_count > 0 and objective_index >= challenge_count:
            player_progress["finished"] = True

    def _player_progress_view(self, data: dict[str, Any]) -> PlayerGameProgress:
        return PlayerGameProgress(
            objective_index=int(data.get("objective_index", 0)),
            progress_percent=float(data.get("progress_percent", 0.0)),
            wpm=float(data.get("wpm", 0.0)),
            accuracy=float(data.get("accuracy", 0.0)),
            streak=int(data.get("streak", 0)),
            attempts_total=int(data.get("attempts_total", 0)),
            attempts_correct=int(data.get("attempts_correct", 0)),
            finished=bool(data.get("finished", False)),
            finished_at=(
                float(data.get("finished_at"))
                if data.get("finished_at") is not None
                else None
            ),
        )

    def _serialize_state_locked(self, room: GameRoom, now: float) -> GameStateView:
        gs = room.game_state
        challenge_count = self._challenge_count(gs)
        round_started_at = float(gs.get("round_started_at", now))

        players: dict[str, PlayerGameProgress] = {}
        for pid in room.players:
            progress = self._ensure_player_progress(gs, pid)
            self._recompute_metrics(progress, challenge_count, round_started_at, now)
            players[pid] = self._player_progress_view(progress)

        return GameStateView(
            status=self._as_status(gs.get("status", GameSessionStatus.RUNNING.value)),
            state_version=int(gs.get("state_version", 0)),
            server_time=now,
            round_started_at=round_started_at,
            round_ends_at=float(gs.get("round_ends_at", now)),
            objective_count=challenge_count,
            challenges=publicize_challenges(gs.get("challenges", [])),
            players=players,
            finished=self._as_status(gs.get("status")) == GameSessionStatus.FINISHED,
            winner_player_id=gs.get("winner_player_id"),
            draw=bool(gs.get("draw", False)),
            end_reason=self._as_end_reason(gs.get("end_reason")),
            finished_at=(
                float(gs.get("finished_at")) if gs.get("finished_at") is not None else None
            ),
        )

    def _ranking_entries_locked(self, room: GameRoom) -> list[dict[str, Any]]:
        gs = room.game_state
        rankings: list[dict[str, Any]] = []
        for pid in room.players:
            progress = self._ensure_player_progress(gs, pid)
            rankings.append(
                {
                    "player_id": pid,
                    "objective_index": int(progress.get("objective_index", 0)),
                    "progress_percent": float(progress.get("progress_percent", 0.0)),
                    "wpm": float(progress.get("wpm", 0.0)),
                    "accuracy": float(progress.get("accuracy", 0.0)),
                    "streak": int(progress.get("streak", 0)),
                    "attempts_total": int(progress.get("attempts_total", 0)),
                    "attempts_correct": int(progress.get("attempts_correct", 0)),
                    "finished": bool(progress.get("finished", False)),
                    "finished_at": progress.get("finished_at"),
                }
            )

        rankings.sort(
            key=lambda item: (
                -int(item.get("objective_index", 0)),
                -float(item.get("accuracy", 0.0)),
                -float(item.get("wpm", 0.0)),
                str(item.get("player_id", "")),
            )
        )
        return rankings

    def _resolve_timeout_or_forfeit_winner_locked(
        self,
        room: GameRoom,
    ) -> tuple[str | None, bool]:
        rankings = self._ranking_entries_locked(room)
        if not rankings:
            return None, True
        if len(rankings) == 1:
            return str(rankings[0]["player_id"]), False

        top = rankings[0]
        second = rankings[1]
        top_tuple = (
            int(top.get("objective_index", 0)),
            float(top.get("accuracy", 0.0)),
            float(top.get("wpm", 0.0)),
        )
        second_tuple = (
            int(second.get("objective_index", 0)),
            float(second.get("accuracy", 0.0)),
            float(second.get("wpm", 0.0)),
        )
        if top_tuple == second_tuple:
            return None, True
        return str(top["player_id"]), False

    def _finish_round_locked(
        self,
        room: GameRoom,
        reason: GameEndReason,
        now: float,
        *,
        winner_player_id: str | None = None,
        draw: bool = False,
        increment_version: bool = True,
    ) -> bool:
        gs = room.game_state
        if self._as_status(gs.get("status")) == GameSessionStatus.FINISHED:
            return False

        if reason in {GameEndReason.TIME, GameEndReason.FORFEIT} and not draw:
            computed_winner, computed_draw = self._resolve_timeout_or_forfeit_winner_locked(
                room
            )
            if winner_player_id is None:
                winner_player_id = computed_winner
            draw = computed_draw

        if draw:
            winner_player_id = None

        gs["status"] = GameSessionStatus.FINISHED.value
        gs["finished_at"] = now
        gs["winner_player_id"] = winner_player_id
        gs["draw"] = draw
        gs["end_reason"] = reason.value

        if increment_version:
            self._increment_state_version(gs)
        return True

    def _resolve_timeout_if_needed_locked(self, room: GameRoom, now: float) -> bool:
        gs = room.game_state
        if self._as_status(gs.get("status")) != GameSessionStatus.RUNNING:
            return False
        round_ends_at = float(gs.get("round_ends_at", now))
        if now < round_ends_at:
            return False
        return self._finish_round_locked(room, GameEndReason.TIME, now)

    def _result_event_locked(self, room: GameRoom) -> dict[str, Any]:
        gs = room.game_state
        return {
            "event": "game_result",
            "room_id": room.id,
            "winner_player_id": gs.get("winner_player_id"),
            "draw": bool(gs.get("draw", False)),
            "end_reason": gs.get("end_reason"),
            "rankings": self._ranking_entries_locked(room),
        }

    def _rejected_response_locked(
        self,
        room: GameRoom,
        now: float,
        *,
        room_id: str,
        player_id: str,
        objective_index: int,
        reason: str,
    ) -> AttemptResponse:
        state = self._serialize_state_locked(room, now)
        return AttemptResponse(
            room_id=room_id,
            player_id=player_id,
            accepted=False,
            reason=reason,
            correct=None,
            objective_index=objective_index,
            state_version=state.state_version,
            game_state=state,
        )

    async def _broadcast_to_players(
        self,
        players: tuple[str, ...] | list[str],
        payload: dict[str, Any],
    ) -> None:
        for pid in players:
            await connection_manager.send_personal_message(pid, payload)

    async def _broadcast_state(self, room: GameRoom, state: GameStateView) -> None:
        await self._broadcast_to_players(
            room.players,
            {
                "event": "game_state_update",
                "room_id": room.id,
                "state_version": state.state_version,
                "game_state": state.model_dump(mode="json"),
            },
        )

    async def ensure_room_state(self, room_id: str) -> GameStateView | None:
        """Apply timeout transitions (if needed) and return public room state."""
        room = await game_room_manager.get_room(room_id)
        if room is None:
            return None

        timed_out = False
        result_event: dict[str, Any] | None = None

        async with self._lock:
            now = time.time()
            timed_out = self._resolve_timeout_if_needed_locked(room, now)
            state = self._serialize_state_locked(room, now)
            if timed_out:
                result_event = self._result_event_locked(room)

        if timed_out:
            await self._broadcast_state(room, state)
            if result_event is not None:
                await self._broadcast_to_players(room.players, result_event)
        return state

    async def get_public_state(self, room: GameRoom) -> GameStateView:
        """Return the latest public state for a room."""
        refreshed = await self.ensure_room_state(room.id)
        if refreshed is not None:
            return refreshed

        now = time.time()
        async with self._lock:
            return self._serialize_state_locked(room, now)

    async def submit_attempt(
        self,
        room_id: str,
        player_id: str,
        objective_index: int,
        keys: list[str],
        attempt_id: str | None = None,
    ) -> AttemptResponse:
        """Apply a player attempt to authoritative state."""
        room = await game_room_manager.get_room(room_id)
        if room is None:
            raise LookupError("Game room not found")

        response: AttemptResponse | None = None
        progress_event: dict[str, Any] | None = None
        penalty_event: dict[str, Any] | None = None
        should_broadcast_state = False
        result_event: dict[str, Any] | None = None

        async with self._lock:
            now = time.time()
            gs = room.game_state

            if self._resolve_timeout_if_needed_locked(room, now):
                response = self._rejected_response_locked(
                    room,
                    now,
                    room_id=room_id,
                    player_id=player_id,
                    objective_index=objective_index,
                    reason="round_finished",
                )
                should_broadcast_state = True
                result_event = self._result_event_locked(room)
            elif player_id not in room.players:
                response = self._rejected_response_locked(
                    room,
                    now,
                    room_id=room_id,
                    player_id=player_id,
                    objective_index=objective_index,
                    reason="invalid_player",
                )
            elif self._as_status(gs.get("status")) != GameSessionStatus.RUNNING:
                response = self._rejected_response_locked(
                    room,
                    now,
                    room_id=room_id,
                    player_id=player_id,
                    objective_index=objective_index,
                    reason="round_finished",
                )
            elif not isinstance(keys, list) or len(keys) == 0:
                response = self._rejected_response_locked(
                    room,
                    now,
                    room_id=room_id,
                    player_id=player_id,
                    objective_index=objective_index,
                    reason="invalid_input_format",
                )
            else:
                receipts = gs.setdefault("attempt_receipts", {}).setdefault(player_id, {})
                if attempt_id and attempt_id in receipts:
                    cached = receipts[attempt_id]
                    state = self._serialize_state_locked(room, now)
                    response = AttemptResponse(
                        room_id=room_id,
                        player_id=player_id,
                        accepted=bool(cached.get("accepted", False)),
                        reason=cached.get("reason"),
                        correct=cached.get("correct"),
                        objective_index=int(
                            cached.get("objective_index", objective_index)
                        ),
                        state_version=int(cached.get("state_version", state.state_version)),
                        game_state=state,
                    )
                else:
                    # Per-player burst limiter: max N attempt events in the last second.
                    now_monotonic = time.monotonic()
                    rate_limit = gs.setdefault("rate_limit", {})
                    stamps = rate_limit.setdefault(player_id, [])
                    while stamps and now_monotonic - stamps[0] > 1.0:
                        stamps.pop(0)
                    stamps.append(now_monotonic)

                    max_attempts = max(1, int(get_settings().max_attempts_per_second))
                    if len(stamps) > max_attempts:
                        response = self._rejected_response_locked(
                            room,
                            now,
                            room_id=room_id,
                            player_id=player_id,
                            objective_index=objective_index,
                            reason="rate_limited",
                        )
                    else:
                        challenge_count = self._challenge_count(gs)
                        progress = self._ensure_player_progress(gs, player_id)
                        expected_index = int(progress.get("objective_index", 0))

                        if objective_index != expected_index:
                            response = self._rejected_response_locked(
                                room,
                                now,
                                room_id=room_id,
                                player_id=player_id,
                                objective_index=expected_index,
                                reason="invalid_objective_index",
                            )
                        else:
                            challenges = gs.get("challenges", [])
                            if expected_index >= len(challenges):
                                response = self._rejected_response_locked(
                                    room,
                                    now,
                                    room_id=room_id,
                                    player_id=player_id,
                                    objective_index=expected_index,
                                    reason="already_finished",
                                )
                            else:
                                expected_keys = self._normalize_keys(
                                    list(challenges[expected_index].get("expectedKeys", []))
                                )
                                provided_keys = self._normalize_keys(keys)
                                correct = expected_keys == provided_keys

                                progress["attempts_total"] = (
                                    int(progress.get("attempts_total", 0)) + 1
                                )
                                if correct:
                                    progress["attempts_correct"] = (
                                        int(progress.get("attempts_correct", 0)) + 1
                                    )
                                    progress["objective_index"] = expected_index + 1
                                    progress["streak"] = int(progress.get("streak", 0)) + 1

                                    if (
                                        challenge_count > 0
                                        and int(progress["objective_index"]) >= challenge_count
                                    ):
                                        progress["finished"] = True
                                        progress["finished_at"] = now
                                        self._finish_round_locked(
                                            room,
                                            GameEndReason.GOAL,
                                            now,
                                            winner_player_id=player_id,
                                            draw=False,
                                            increment_version=False,
                                        )
                                else:
                                    progress["streak"] = 0

                                self._recompute_metrics(
                                    progress,
                                    challenge_count,
                                    float(gs.get("round_started_at", now)),
                                    now,
                                )
                                self._increment_state_version(gs)

                                state = self._serialize_state_locked(room, now)
                                should_broadcast_state = True
                                if state.finished:
                                    result_event = self._result_event_locked(room)

                                progress_event = {
                                    "event": "progress_update",
                                    "room_id": room.id,
                                    "player_id": player_id,
                                    "index": int(progress.get("objective_index", 0)),
                                    "score": int(progress.get("attempts_correct", 0)),
                                    "correct": correct,
                                }
                                if not correct:
                                    penalty_event = {
                                        "event": "penalty",
                                        "message": "incorrect_input",
                                        "score": int(progress.get("attempts_correct", 0)),
                                    }

                                response = AttemptResponse(
                                    room_id=room_id,
                                    player_id=player_id,
                                    accepted=True,
                                    reason=None,
                                    correct=correct,
                                    objective_index=int(progress.get("objective_index", 0)),
                                    state_version=state.state_version,
                                    game_state=state,
                                )

                if attempt_id and response is not None and attempt_id not in receipts:
                    receipts[attempt_id] = {
                        "accepted": response.accepted,
                        "reason": response.reason,
                        "correct": response.correct,
                        "objective_index": response.objective_index,
                        "state_version": response.state_version,
                    }

        if response is None:
            raise RuntimeError("attempt response was not generated")

        if penalty_event is not None:
            await connection_manager.send_personal_message(player_id, penalty_event)
        if progress_event is not None:
            await self._broadcast_to_players(room.players, progress_event)
        if should_broadcast_state:
            await self._broadcast_state(room, response.game_state)
        if result_event is not None:
            await self._broadcast_to_players(room.players, result_event)
        return response

    async def resolve_forfeit(self, room_id: str, forfeiting_player_id: str) -> None:
        """Finish a running round due to player disconnect/forfeit."""
        room = await game_room_manager.get_room(room_id)
        if room is None:
            return

        state: GameStateView | None = None
        result_event: dict[str, Any] | None = None

        async with self._lock:
            now = time.time()
            changed = self._finish_round_locked(room, GameEndReason.FORFEIT, now)
            if not changed:
                return
            room.game_state["forfeit_player_id"] = forfeiting_player_id
            state = self._serialize_state_locked(room, now)
            result_event = self._result_event_locked(room)
            result_event["forfeit_player_id"] = forfeiting_player_id

        await self._broadcast_state(room, state)
        if result_event is not None:
            await self._broadcast_to_players(room.players, result_event)

    async def process_input(self, player_id: str, payload: dict[str, Any]) -> None:
        """Backward-compatible WebSocket input handler."""
        keys = payload.get("keys")
        if not isinstance(keys, list):
            await connection_manager.send_personal_message(
                player_id,
                {"event": "error", "message": "invalid_input_format"},
            )
            return

        player = await connection_manager.get_player(player_id)
        if player is None or player.current_room is None:
            await connection_manager.send_personal_message(
                player_id,
                {"event": "error", "message": "not_in_game"},
            )
            return

        room_id = payload.get("room_id") or player.current_room
        room = await game_room_manager.get_room(room_id)
        if room is None:
            await connection_manager.send_personal_message(
                player_id,
                {"event": "error", "message": "room_not_found"},
            )
            return

        raw_index = payload.get("objective_index")
        if isinstance(raw_index, int):
            objective_index = raw_index
        else:
            objective_index = int(
                room.game_state.get("progress", {})
                .get(player_id, {})
                .get("objective_index", 0)
            )

        try:
            result = await self.submit_attempt(
                room_id=room_id,
                player_id=player_id,
                objective_index=objective_index,
                keys=keys,
                attempt_id=payload.get("attempt_id"),
            )
        except LookupError:
            await connection_manager.send_personal_message(
                player_id,
                {"event": "error", "message": "room_not_found"},
            )
            return

        if not result.accepted and result.reason == "rate_limited":
            await connection_manager.send_personal_message(
                player_id,
                {"event": "spam_blocked", "message": "too_many_inputs"},
            )

        await connection_manager.send_personal_message(
            player_id,
            {
                "event": "attempt_result",
                **result.model_dump(mode="json"),
            },
        )


game_engine = GameEngine()
