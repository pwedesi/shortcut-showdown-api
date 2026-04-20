"""Tests for input validation, penalties, spam handling, and ranking."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from app.core.game_room_manager import game_room_manager
from app.main import app


def test_correct_input_advances_player() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]
        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": pid})

        # receive challenges event
        msg = ws.receive_json()
        assert msg["event"] == "challenges"

        room = asyncio.run(game_room_manager.get_room(lobby_id))
        expected = room.game_state["challenges"][0]["expectedKeys"]

        ws.send_text(json.dumps({"event": "input", "keys": expected}))

        # wait for progress_update
        while True:
            m = ws.receive_json()
            if m.get("event") == "progress_update":
                assert m["player_id"] == pid
                assert m["index"] == 1
                assert m["score"] == 1
                break


def test_incorrect_input_penalized() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]
        client.post(f"/lobbies/{lobby_id}/start", json={"player_id": pid})

        # receive challenges event
        msg = ws.receive_json()
        assert msg["event"] == "challenges"

        # send wrong input
        ws.send_text(json.dumps({"event": "input", "keys": ["wrong"]}))

        # expect penalty event
        while True:
            m = ws.receive_json()
            if m.get("event") == "penalty":
                assert "score" in m
                break


def test_winner_and_rankings_broadcasted() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            la = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{la}/join", json={"player_id": p2})
            client.post(f"/lobbies/{la}/start", json={"player_id": p1})

            # drain initial challenges messages
            ws1.receive_json()
            ws2.receive_json()

            # shrink server-side challenge list to a single challenge for quick finish
            async def shrink():
                room = await game_room_manager.get_room(la)
                assert room is not None
                room.game_state["challenges"] = room.game_state["challenges"][:1]

            asyncio.run(shrink())

            room = asyncio.run(game_room_manager.get_room(la))
            expected = room.game_state["challenges"][0]["expectedKeys"]

            # p1 submits correct answer and should trigger a game_result broadcast
            ws1.send_text(json.dumps({"event": "input", "keys": expected}))

            got1 = None
            got2 = None
            for _ in range(10):
                m = ws1.receive_json()
                if m.get("event") == "game_result":
                    got1 = m
                    break
            for _ in range(10):
                m = ws2.receive_json()
                if m.get("event") == "game_result":
                    got2 = m
                    break

            assert got1 is not None and got2 is not None
            rankings = got1["rankings"]
            assert rankings[0]["player_id"] == p1
