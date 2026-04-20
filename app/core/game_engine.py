"""Game engine: validate shortcut inputs, track progress, and produce rankings.

This module enforces server-side validation, simple anti-spam, penalties,
and ranking/broadcasts when players finish the challenge sequence.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager


class GameEngine:
    def __init__(self) -> None:
        # coarse lock to serialize updates per server process
        self._lock = asyncio.Lock()

    async def process_input(self, player_id: str, payload: Dict[str, Any]) -> None:
        """Validate a player's input and update game state accordingly.

        Expected payload: {"event": "input", "keys": ["ctrl","c"]}
        """
        keys = payload.get("keys")
        if not isinstance(keys, list):
            await connection_manager.send_personal_message(
                player_id, {"event": "error", "message": "invalid_input_format"}
            )
            return

        keys_norm = [str(k).lower() for k in keys]

        player = await connection_manager.get_player(player_id)
        if player is None or player.current_room is None:
            await connection_manager.send_personal_message(
                player_id, {"event": "error", "message": "not_in_game"}
            )
            return

        room = await game_room_manager.get_room(player.current_room)
        if room is None:
            await connection_manager.send_personal_message(
                player_id, {"event": "error", "message": "room_not_found"}
            )
            return

        async with self._lock:
            gs: Dict[str, Any] = room.game_state
            challenges: List[Dict[str, Any]] = gs.get("challenges", [])

            # initialize per-player progress state
            progress = gs.setdefault("progress", {})
            ps = progress.setdefault(player_id, {"index": 0, "score": 0, "finished": False})

            # simple rate limiting: max 5 inputs per 1 second
            rate = gs.setdefault("rate_limit", {})
            now = time.monotonic()
            timestamps: List[float] = rate.setdefault(player_id, [])
            # prune older than 1s
            while timestamps and now - timestamps[0] > 1.0:
                timestamps.pop(0)
            timestamps.append(now)
            if len(timestamps) > 5:
                await connection_manager.send_personal_message(
                    player_id, {"event": "spam_blocked", "message": "too_many_inputs"}
                )
                return

            idx = ps.get("index", 0)
            if idx >= len(challenges):
                await connection_manager.send_personal_message(
                    player_id, {"event": "finished", "message": "already_finished"}
                )
                return

            expected = challenges[idx].get("expectedKeys", [])
            expected_norm = [str(k).lower() for k in expected]

            if set(expected_norm) == set(keys_norm):
                # correct
                ps["index"] = idx + 1
                ps["score"] = ps.get("score", 0) + 1
                if ps["index"] >= len(challenges):
                    ps["finished"] = True
                    finished = gs.setdefault("finished_order", [])
                    if player_id not in finished:
                        finished.append(player_id)
                        gs.setdefault("finish_times", {})[player_id] = now

                # broadcast progress update to all players in room
                update = {
                    "event": "progress_update",
                    "player_id": player_id,
                    "index": ps["index"],
                    "score": ps["score"],
                }
                for pid in room.players:
                    await connection_manager.send_personal_message(pid, update)

                # if finished, broadcast rankings
                if ps.get("finished"):
                    await self._broadcast_rankings(room)
            else:
                # incorrect input -> penalty
                ps["score"] = max(0, ps.get("score", 0) - 1)
                await connection_manager.send_personal_message(
                    player_id,
                    {"event": "penalty", "message": "incorrect_input", "score": ps["score"]},
                )
                # also broadcast current progress so other players see the penalty
                update = {
                    "event": "progress_update",
                    "player_id": player_id,
                    "index": ps["index"],
                    "score": ps["score"],
                }
                for pid in room.players:
                    await connection_manager.send_personal_message(pid, update)

    async def _broadcast_rankings(self, room: "GameRoom") -> None:
        gs: Dict[str, Any] = room.game_state
        progress: Dict[str, Any] = gs.get("progress", {})
        finish_times: Dict[str, float] = gs.get("finish_times", {})

        rankings: List[Dict[str, Any]] = []
        for pid in room.players:
            p = progress.get(pid, {"index": 0, "score": 0, "finished": False})
            rankings.append(
                {
                    "player_id": pid,
                    "score": p.get("score", 0),
                    "index": p.get("index", 0),
                    "finished": p.get("finished", False),
                    "finish_time": finish_times.get(pid),
                }
            )

        def sort_key(r: Dict[str, Any]) -> tuple:
            return (
                -int(r.get("finished", False)),
                -int(r.get("score", 0)),
                r.get("finish_time") if r.get("finish_time") is not None else float("inf"),
            )

        rankings.sort(key=sort_key)

        msg = {"event": "game_result", "room_id": room.id, "rankings": rankings}
        for pid in room.players:
            await connection_manager.send_personal_message(pid, msg)


game_engine = GameEngine()
