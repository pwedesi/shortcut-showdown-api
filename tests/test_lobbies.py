"""Tests for lobby REST API and lobby_manager behavior."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.connection_manager import connection_manager
from app.core.lobby_manager import lobby_manager
from app.main import app
from app.models.player import PlayerStatus


def test_create_lobby_returns_waiting_and_single_player() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        res = client.post("/lobbies", json={"player_id": pid})
        assert res.status_code == 201
        body = res.json()
        s = get_settings()
        update = ws.receive_json()
        assert update["type"] == "lobby_updated"
        assert update["lobby_id"] == body["id"]
        assert update["lobby"]["players"] == [
            {
                "player_id": pid,
                "display_name": pid,
                "is_leader": True,
                "is_ready": False,
            }
        ]
        assert update["lobby"]["challenge_count"] == s.challenge_count
        assert update["lobby"]["round_duration_seconds"] == s.round_duration_seconds
        assert (
            update["lobby"]["max_attempts_per_second"] == s.max_attempts_per_second
        )
        assert "id" in body
        assert body["players"] == [
            {
                "player_id": pid,
                "display_name": pid,
                "is_leader": True,
                "is_ready": False,
            }
        ]
        assert body["status"] == "waiting"
        assert body["challenge_count"] == s.challenge_count
        assert body["round_duration_seconds"] == s.round_duration_seconds
        assert body["max_attempts_per_second"] == s.max_attempts_per_second
        assert len(body["id"]) == 7
        assert all(
            c in "ABCDEFGHJKMNPQRSTUVWXYZ23456789" for c in body["id"]
        )

        async def check_player() -> None:
            p = await connection_manager.get_player(pid)
            assert p is not None
            assert p.status == PlayerStatus.LOBBY
            assert p.current_room == body["id"]

        asyncio.run(check_player())


def test_join_makes_full_and_get_lists_players() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            created = client.post("/lobbies", json={"player_id": p1})
            lobby_id = created.json()["id"]

            s = get_settings()
            created_update = ws1.receive_json()
            assert created_update["type"] == "lobby_updated"
            assert created_update["lobby"]["players"] == [
                {
                    "player_id": p1,
                    "display_name": p1,
                    "is_leader": True,
                    "is_ready": False,
                },
            ]
            assert created_update["lobby"]["challenge_count"] == s.challenge_count
            assert (
                created_update["lobby"]["round_duration_seconds"]
                == s.round_duration_seconds
            )
            assert (
                created_update["lobby"]["max_attempts_per_second"]
                == s.max_attempts_per_second
            )

            joined = client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})
            assert joined.status_code == 200
            assert joined.json()["status"] == "full"
            j = joined.json()
            jbody = j["players"]
            assert [player["player_id"] for player in jbody] == [p1, p2]
            assert jbody[0]["is_leader"] is True
            assert jbody[1]["is_leader"] is False
            assert j["challenge_count"] == s.challenge_count
            assert j["round_duration_seconds"] == s.round_duration_seconds
            assert j["max_attempts_per_second"] == s.max_attempts_per_second

            update1 = ws1.receive_json()
            update2 = ws2.receive_json()
            assert update1["type"] == "lobby_updated"
            assert update1["lobby"]["players"][1]["player_id"] == p2
            assert update2["type"] == "lobby_updated"
            assert update2["lobby"]["players"][1]["player_id"] == p2

            got = client.get(f"/lobbies/{lobby_id}")
            assert got.status_code == 200
            assert [player["player_id"] for player in got.json()["players"]] == [p1, p2]


def test_join_when_full_returns_409() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]
            with client.websocket_connect("/ws") as ws3:
                p3 = ws3.receive_json()["player_id"]

                lobby_id = client.post("/lobbies", json={"player_id": p1}).json()[
                    "id"
                ]
                client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

                res = client.post(
                    f"/lobbies/{lobby_id}/join",
                    json={"player_id": p3},
                )
                assert res.status_code == 409


def test_leave_last_player_deletes_lobby() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        created = client.post("/lobbies", json={"player_id": pid})
        lobby_id = created.json()["id"]

        le = client.post(f"/lobbies/{lobby_id}/leave", json={"player_id": pid})
        assert le.status_code == 204

        assert client.get(f"/lobbies/{lobby_id}").status_code == 404

        async def check_gone() -> None:
            assert await lobby_manager.get_lobby(lobby_id) is None

        asyncio.run(check_gone())


def test_creator_leave_promotes_new_leader() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

            client.post(f"/lobbies/{lobby_id}/leave", json={"player_id": p1})

            # p2 must stay connected or disconnect cleanup empties the lobby
            got = client.get(f"/lobbies/{lobby_id}")
            assert got.status_code == 200
            pl = got.json()["players"]
            assert len(pl) == 1
            assert pl[0]["player_id"] == p2
            assert pl[0]["is_leader"] is True

            async def check_lobby() -> None:
                lobby = await lobby_manager.get_lobby(lobby_id)
                assert lobby is not None
                assert lobby.leader_id == p2

            asyncio.run(check_lobby())


def test_leave_updates_remaining_player_status() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

            client.post(f"/lobbies/{lobby_id}/leave", json={"player_id": p2})

        async def check() -> None:
            p = await connection_manager.get_player(p1)
            assert p is not None
            assert p.status == PlayerStatus.LOBBY
            assert p.current_room == lobby_id

            lobby = await lobby_manager.get_lobby(lobby_id)
            assert lobby is not None
            assert lobby.players == (p1,)
            assert lobby.leader_id == p1
            assert lobby.status.value == "waiting"

        asyncio.run(check())


def test_websocket_disconnect_removes_player_from_lobby() -> None:
    """Closing the socket runs cleanup so the lobby no longer lists that player."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

    async def after_both_closed() -> None:
        assert await lobby_manager.get_lobby(lobby_id) is None

    asyncio.run(after_both_closed())


def test_unknown_player_create_returns_404() -> None:
    client = TestClient(app)
    res = client.post("/lobbies", json={"player_id": "not-a-real-id"})
    assert res.status_code == 404
