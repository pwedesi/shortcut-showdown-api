"""Tests for player callsign registration and lobby identity responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.player import DISPLAY_NAME_MAX_LENGTH


def _players_by_id(players: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {player["player_id"]: player for player in players}


def test_set_display_name_is_returned_in_lobby_payload() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            set_1 = client.patch(
                f"/players/{p1}",
                json={"display_name": "OPERATOR_01"},
            )
            assert set_1.status_code == 200
            assert set_1.json() == {
                "player_id": p1,
                "display_name": "OPERATOR_01",
            }

            set_2 = client.patch(
                f"/players/{p2}",
                json={"display_name": "MAVERICK"},
            )
            assert set_2.status_code == 200

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

            got = client.get(f"/lobbies/{lobby_id}")
            assert got.status_code == 200
            roster = _players_by_id(got.json()["players"])
            assert roster[p1]["display_name"] == "OPERATOR_01"
            assert roster[p2]["display_name"] == "MAVERICK"


@pytest.mark.parametrize(
    ("display_name", "expected_detail"),
    [
        ("", "display_name_empty"),
        ("   ", "display_name_empty"),
        ("A" * (DISPLAY_NAME_MAX_LENGTH + 1), "display_name_too_long"),
        ("HELLO!", "display_name_invalid_characters"),
    ],
)
def test_invalid_display_name_returns_400(
    display_name: str,
    expected_detail: str,
) -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]

        res = client.patch(
            f"/players/{pid}",
            json={"display_name": display_name},
        )
        assert res.status_code == 400
        assert res.json()["detail"] == expected_detail


def test_unknown_player_id_returns_404() -> None:
    client = TestClient(app)

    res = client.patch(
        "/players/not-a-real-player",
        json={"display_name": "OPERATOR_01"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "player_not_found"


def test_duplicate_display_names_are_allowed_in_same_lobby() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        p1 = ws1.receive_json()["player_id"]
        with client.websocket_connect("/ws") as ws2:
            p2 = ws2.receive_json()["player_id"]

            client.patch(f"/players/{p1}", json={"display_name": "ACE"})
            client.patch(f"/players/{p2}", json={"display_name": "ACE"})

            lobby_id = client.post("/lobbies", json={"player_id": p1}).json()["id"]
            client.post(f"/lobbies/{lobby_id}/join", json={"player_id": p2})

            got = client.get(f"/lobbies/{lobby_id}")
            assert got.status_code == 200
            roster = _players_by_id(got.json()["players"])
            assert roster[p1]["display_name"] == "ACE"
            assert roster[p2]["display_name"] == "ACE"


def test_display_name_can_change_mid_lobby() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        pid = ws.receive_json()["player_id"]

        client.patch(f"/players/{pid}", json={"display_name": "ROOKIE"})
        lobby_id = client.post("/lobbies", json={"player_id": pid}).json()["id"]

        updated = client.patch(f"/players/{pid}", json={"display_name": "VETERAN"})
        assert updated.status_code == 200

        got = client.get(f"/lobbies/{lobby_id}")
        assert got.status_code == 200
        assert got.json()["players"] == [
            {
                "player_id": pid,
                "display_name": "VETERAN",
            }
        ]
