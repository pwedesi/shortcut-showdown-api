"""Tests for ConnectionManager."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.connection_manager import ConnectionManager, connection_manager
from app.main import app
from app.models.player import PlayerStatus


def _mock_websocket() -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


def test_connect_registers_and_returns_id() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        cid = await manager.connect(ws)
        assert isinstance(cid, str) and len(cid) > 0
        ws.accept.assert_awaited_once()

    asyncio.run(run())


def test_duplicate_same_socket_returns_same_id() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        first = await manager.connect(ws)
        second = await manager.connect(ws)
        assert first == second
        ws.accept.assert_awaited_once()

    asyncio.run(run())


def test_disconnect_removes_connection() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        cid = await manager.connect(ws)
        await manager.disconnect(cid)
        async with manager._lock:
            assert cid not in manager._players
        await manager.broadcast("ping")
        ws.send_text.assert_not_called()

    asyncio.run(run())


def test_broadcast_sends_to_all_connections() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws1 = _mock_websocket()
        ws2 = _mock_websocket()
        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.broadcast("hello")
        ws1.send_text.assert_called_once_with("hello")
        ws2.send_text.assert_called_once_with("hello")

    asyncio.run(run())


def test_broadcast_json_dict() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        await manager.connect(ws)
        payload = {"event": "x", "data": 1}
        await manager.broadcast(payload)
        ws.send_json.assert_called_once_with(payload)

    asyncio.run(run())


def test_send_personal_message_targets_one() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws1 = _mock_websocket()
        ws2 = _mock_websocket()
        id1 = await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.send_personal_message(id1, "only-one")
        ws1.send_text.assert_called_once_with("only-one")
        ws2.send_text.assert_not_called()

    asyncio.run(run())


def test_broadcast_drops_dead_socket() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        ws.send_text = AsyncMock(side_effect=RuntimeError("closed"))
        cid = await manager.connect(ws)
        await manager.broadcast("x")
        async with manager._lock:
            assert cid not in manager._connections

    asyncio.run(run())


def test_ws_endpoint_echo_integration() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["event"] == "connect"
        assert first["type"] == "connect"
        assert first["v"] == 1
        assert first["payload"]["player_id"] == first["player_id"]
        assert "player_id" in first
        pid = first["player_id"]
        assert isinstance(pid, str) and len(pid) > 0

        async def check_player() -> None:
            player = await connection_manager.get_player(pid)
            assert player is not None
            assert player.id == pid
            assert player.status == PlayerStatus.IDLE

        asyncio.run(check_player())
        ws.send_text("hello")
        second = ws.receive_json()
        assert second["event"] == "message"
        assert second["type"] == "message"
        assert second["payload"]["data"] == "hello"
        assert second["data"] == "hello"


def test_websocket_join_lobby_returns_snapshot() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]

        # consume the lobby broadcast from the create call
        ws.receive_json()

        ws.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "join_lobby",
                    "payload": {"lobby_id": lobby_id, "player_id": pid},
                }
            )
        )

        ack = ws.receive_json()
        snapshot = ws.receive_json()
        assert ack["type"] == "subscription_ack"
        assert snapshot["type"] == "lobby_snapshot"
        assert snapshot["lobby_id"] == lobby_id
        s = get_settings()
        assert snapshot["lobby"]["players"] == [
            {"player_id": pid, "display_name": pid, "is_leader": True},
        ]
        assert snapshot["lobby"]["challenge_count"] == s.challenge_count
        assert snapshot["lobby"]["round_duration_seconds"] == s.round_duration_seconds
        assert (
            snapshot["lobby"]["max_attempts_per_second"] == s.max_attempts_per_second
        )


def test_connect_creates_player() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        cid = await manager.connect(ws)
        p = await manager.get_player(cid)
        assert p is not None
        assert p.id == cid
        assert p.display_name == ""
        assert p.status == PlayerStatus.IDLE
        assert p.current_room is None

    asyncio.run(run())


def test_get_player_by_id() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        cid = await manager.connect(ws)
        assert await manager.get_player(cid) is not None
        assert await manager.get_player("unknown") is None

    asyncio.run(run())


def test_update_player_state() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        cid = await manager.connect(ws)
        updated = await manager.update_player(
            cid,
            display_name="alice",
            status=PlayerStatus.LOBBY,
            current_room="room-1",
        )
        assert updated is not None
        assert updated.display_name == "alice"
        assert updated.status == PlayerStatus.LOBBY
        assert updated.current_room == "room-1"
        again = await manager.get_player(cid)
        assert again == updated

    asyncio.run(run())


def test_update_player_in_game_and_clear_room() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        ws = _mock_websocket()
        cid = await manager.connect(ws)
        await manager.update_player(cid, current_room="r1")
        ingame = await manager.update_player(cid, status=PlayerStatus.IN_GAME)
        assert ingame is not None
        assert ingame.status == PlayerStatus.IN_GAME
        assert ingame.current_room == "r1"
        cleared = await manager.update_player(cid, current_room=None)
        assert cleared is not None
        assert cleared.current_room is None

    asyncio.run(run())


def test_module_singleton_is_connection_manager() -> None:
    assert isinstance(connection_manager, ConnectionManager)
