"""Tests for game room creation from lobby and isolation."""

from __future__ import annotations

import asyncio

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
            assert body["game_state"] == {}

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
