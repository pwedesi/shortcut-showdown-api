import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.core.lobby_manager import lobby_manager
from app.core.game_engine import game_engine
from app.core.websocket_protocol import build_error, build_message, parse_inbound_message

router = APIRouter(tags=["websocket"])


async def _send_subscription_snapshot(websocket_id: str, scope: str, scope_id: str) -> None:
    if scope == "lobby":
        lobby = await lobby_manager.get_lobby(scope_id)
        if lobby is None:
            await connection_manager.send_personal_message(websocket_id, build_error("lobby_not_found"))
            return

        players: list[dict[str, str]] = []
        for player_id in lobby.players:
            player = await connection_manager.get_player(player_id)
            display_name = player_id
            if player is not None and player.display_name:
                display_name = player.display_name
            players.append({"player_id": player_id, "display_name": display_name})

        await connection_manager.send_personal_message(
            websocket_id,
            build_message(
                "lobby_snapshot",
                {
                    "lobby_id": lobby.id,
                    "lobby": {
                        "id": lobby.id,
                        "players": players,
                        "status": lobby.status.value,
                    },
                },
            ),
        )
        return

    room = await game_room_manager.get_room(scope_id)
    if room is None:
        await connection_manager.send_personal_message(websocket_id, build_error("room_not_found"))
        return

    state = await game_engine.get_public_state(room)
    await connection_manager.send_personal_message(
        websocket_id,
        build_message(
            "room_snapshot",
            {
                "room_id": room.id,
                "players": list(room.players),
                "locked": room.locked,
                "game_state": state.model_dump(mode="json"),
            },
        ),
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time channel: connect, echo received text messages, clean disconnect."""
    connection_id = await connection_manager.connect(websocket)
    try:
        await connection_manager.send_personal_message(
            connection_id,
            build_message(
                "connect",
                {
                    "message": "connected to Shortcut Showdown API",
                    "player_id": connection_id,
                    "supported_versions": [1],
                },
            ),
        )
        while True:
            text = await websocket.receive_text()
            # try to parse JSON messages with structured events
            try:
                payload = json.loads(text)
            except Exception:
                await connection_manager.send_personal_message(
                    connection_id,
                    build_message("message", {"data": text}),
                )
                continue

            event, message, version = parse_inbound_message(payload)
            if version is not None and str(version) != "1":
                await connection_manager.send_personal_message(
                    connection_id,
                    build_error("unsupported_version"),
                )
                continue

            # route input events to the game engine
            if event in {"input", "attempt"}:
                await game_engine.process_input(connection_id, message)
            elif event == "join_lobby":
                player_id = str(message.get("player_id") or connection_id)
                if player_id != connection_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("stale_player_id"),
                    )
                    continue

                lobby_id = message.get("lobby_id")
                if not isinstance(lobby_id, str) or not lobby_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("invalid_lobby_id"),
                    )
                    continue

                lobby = await lobby_manager.get_lobby(lobby_id)
                if lobby is None:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("lobby_not_found"),
                    )
                    continue

                player = await connection_manager.get_player(connection_id)
                if player is None or player.current_room != lobby_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("forbidden_action"),
                    )
                    continue

                await connection_manager.set_subscription(connection_id, "lobby", lobby_id)
                await connection_manager.clear_subscription(connection_id, "room")
                await connection_manager.send_personal_message(
                    connection_id,
                    build_message(
                        "subscription_ack",
                        {
                            "scope": "lobby",
                            "scope_id": lobby_id,
                            "player_id": connection_id,
                        },
                    ),
                )
                await _send_subscription_snapshot(connection_id, "lobby", lobby_id)
            elif event == "join_room":
                player_id = str(message.get("player_id") or connection_id)
                if player_id != connection_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("stale_player_id"),
                    )
                    continue

                room_id = message.get("room_id")
                if not isinstance(room_id, str) or not room_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("invalid_room_id"),
                    )
                    continue

                room = await game_room_manager.get_room(room_id)
                if room is None:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("room_not_found"),
                    )
                    continue

                player = await connection_manager.get_player(connection_id)
                if player is None or player.current_room != room_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("forbidden_action"),
                    )
                    continue

                await connection_manager.set_subscription(connection_id, "room", room_id)
                await connection_manager.clear_subscription(connection_id, "lobby")
                await connection_manager.send_personal_message(
                    connection_id,
                    build_message(
                        "subscription_ack",
                        {
                            "scope": "room",
                            "scope_id": room_id,
                            "player_id": connection_id,
                        },
                    ),
                )
                await _send_subscription_snapshot(connection_id, "room", room_id)
            elif event == "sync_state":
                room_id = message.get("room_id")
                if not isinstance(room_id, str) or not room_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("invalid_room_id"),
                    )
                    continue

                room = await game_room_manager.get_room(room_id)
                if room is None:
                    await connection_manager.send_personal_message(
                        connection_id,
                        build_error("room_not_found"),
                    )
                    continue

                state = await game_engine.get_public_state(room)
                await connection_manager.send_personal_message(
                    connection_id,
                    build_message(
                        "game_state_sync",
                        {
                            "room_id": room.id,
                            "state_version": state.state_version,
                            "game_state": state.model_dump(mode="json"),
                        },
                    ),
                )
            else:
                await connection_manager.send_personal_message(
                    connection_id,
                    build_message("message", {"data": payload}),
                )
    except WebSocketDisconnect:
        pass
    finally:
        await lobby_manager.remove_player_from_all_lobbies(connection_id)
        await game_room_manager.remove_player_from_all_rooms(connection_id)
        await connection_manager.disconnect(connection_id)
