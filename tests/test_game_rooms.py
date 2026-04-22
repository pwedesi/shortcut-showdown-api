"""Tests for game room creation from lobby and isolation."""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.main import app
from app.models.player import PlayerStatus


def test_start_converts_lobby_to_game_room_and_locks() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

            res = client.post(
                f"/lobbies/{lobby_id}/start",
                json={"player_id": p1},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["id"] == lobby_id
            assert body["players"] == [p1, p2]
            assert body["locked"] is True
            # a shared sequence of shortcut challenges should be present
            assert "challenges" in body["game_state"]
            challenges = body["game_state"]["challenges"]
            assert isinstance(challenges, list)
            assert len(challenges) >= 10
            for ch in challenges:
                assert "prompt" in ch
                assert "expectedKeys" not in ch

            assert client.get(f"/lobbies/{lobby_id}").status_code == 404

            got = client.get(f"/game-rooms/{lobby_id}")
            assert got.status_code == 200
            assert got.json()["locked"] is True


def test_start_assigns_players_in_game_and_room() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]

        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": pid})

        async def check() -> None:
            p = await connection_manager.get_player(pid)
            assert p is not None
            assert p.status == PlayerStatus.IN_GAME
            assert p.current_room == lobby_id

        asyncio.run(check())


def test_two_game_rooms_are_isolated() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        a1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            a2 = ws2.receive_json()["player_id"]
            with client.websocket_connect("/ws") as ws3:
                b1 = ws3.receive_json()["player_id"]
                with client.websocket_connect("/ws") as ws4:
                    b2 = ws4.receive_json()["player_id"]

                    la = client.post("/lobbies", json={"player_id": a1}).json()["id"]
                    client.post(f"/lobbies/{la}/join", json={"player_id": a2})
                    lb = client.post("/lobbies", json={"player_id": b1}).json()["id"]
                    client.post(f"/lobbies/{lb}/join", json={"player_id": b2})

                    client.post(f"/lobbies/{la}/start", json={"player_id": a1})
                    client.post(f"/lobbies/{lb}/start", json={"player_id": b1})

                    ga = client.get(f"/game-rooms/{la}").json()
                    gb = client.get(f"/game-rooms/{lb}").json()
                    assert set(ga["players"]) == {a1, a2}
                    assert set(gb["players"]) == {b1, b2}
                    assert la != lb


def test_start_not_in_lobby_returns_400() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            res = client.post(
                f"/lobbies/{lobby_id}/start",
                json={"player_id": p2},
            )
            assert res.status_code == 400


def test_websocket_disconnect_removes_player_from_game_room() -> None:
    client = TestClient(app)
    with (
        client.websocket_connect("/ws") as ws1,
        client.websocket_connect("/ws") as ws2,
    ):
        p1 = ws1.receive_json()["player_id"]
        p2 = ws2.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
        client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})
        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": p1})

    async def after_close() -> None:
        assert await game_room_manager.get_room(lobby_id) is None

    asyncio.run(after_close())


def test_game_state_contract_has_authoritative_fields() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]
        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": pid})

        got = client.get(f"/game-rooms/{lobby_id}")
        assert got.status_code == 200
        body = got.json()

        state = body["game_state"]
        assert state["status"] == "running"
        assert state["finished"] is False
        assert "state_version" in state
        assert "server_time" in state
        assert "round_started_at" in state
        assert "round_ends_at" in state
        assert "objective_count" in state
        assert "players" in state

        progress = state["players"][pid]
        assert "objective_index" in progress
        assert "progress_percent" in progress
        assert "wpm" in progress
        assert "accuracy" in progress
        assert "streak" in progress


def test_rest_attempt_write_path_is_authoritative_and_idempotent() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]
        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": pid})

        # drain startup events
        ws.receive_json()
        ws.receive_json()

        room = asyncio.run(game_room_manager.get_room(lobby_id))
        assert room is not None
        expected = room.game_state["challenges"][0]["expectedKeys"]

        payload = {
            "player_id": pid,
            "objective_index": 0,
            "keys": expected,
            "attempt_id": "attempt-1",
        }
        first = client.post(f"/game-rooms/{lobby_id}/attempts", json=payload)
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["accepted"] is True
        assert first_body["correct"] is True
        assert first_body["objective_index"] == 1

        # replay same idempotency key; objective index should not advance twice
        second = client.post(f"/game-rooms/{lobby_id}/attempts", json=payload)
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["accepted"] is True
        assert second_body["objective_index"] == 1

        got = client.get(f"/game-rooms/{lobby_id}")
        assert got.status_code == 200
        progress = got.json()["game_state"]["players"][pid]
        assert progress["objective_index"] == 1


def test_goal_end_condition_is_resolved_server_side() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})
            client.post(f"/lobbies/{lobby_id}/start", json={"player_id": p1})

            # shrink to one objective so first correct attempt ends the round by goal
            async def shrink() -> None:
                room = await game_room_manager.get_room(lobby_id)
                assert room is not None
                room.game_state["challenges"] = room.game_state["challenges"][:1]

            asyncio.run(shrink())
            room = asyncio.run(game_room_manager.get_room(lobby_id))
            assert room is not None
            expected = room.game_state["challenges"][0]["expectedKeys"]

            result = client.post(
                f"/game-rooms/{lobby_id}/attempts",
                json={
                    "player_id": p1,
                    "objective_index": 0,
                    "keys": expected,
                    "attempt_id": "goal-attempt",
                },
            )
            assert result.status_code == 200
            state = result.json()["game_state"]
            assert state["status"] == "finished"
            assert state["end_reason"] == "goal"
            assert state["winner_player_id"] == p1
            assert state["draw"] is False


def test_timeout_end_condition_is_resolved_on_snapshot() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})
            client.post(f"/lobbies/{lobby_id}/start", json={"player_id": p1})

            async def expire() -> None:
                room = await game_room_manager.get_room(lobby_id)
                assert room is not None
                room.game_state["round_ends_at"] = time.time() - 1

            asyncio.run(expire())

            got = client.get(f"/game-rooms/{lobby_id}")
            assert got.status_code == 200
            state = got.json()["game_state"]
            assert state["status"] == "finished"
            assert state["end_reason"] == "time"
            assert state["finished"] is True
            assert state["draw"] is True
            assert state["winner_player_id"] is None


def test_invalid_objective_index_is_rejected() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]
        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": pid})

        room = asyncio.run(game_room_manager.get_room(lobby_id))
        assert room is not None
        expected = room.game_state["challenges"][0]["expectedKeys"]

        res = client.post(
            f"/game-rooms/{lobby_id}/attempts",
            json={
                "player_id": pid,
                "objective_index": 9,
                "keys": expected,
                "attempt_id": "bad-index",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["accepted"] is False
        assert body["reason"] == "invalid_objective_index"
