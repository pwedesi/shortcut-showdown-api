from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.core.lobby_manager import lobby_manager
from app.core.game_engine import game_engine

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time channel: connect, echo received text messages, clean disconnect."""
    connection_id = await connection_manager.connect(websocket)
    try:
        await connection_manager.send_personal_message(
            connection_id,
            {
                "event": "connect",
                "message": "connected to Shortcut Showdown API",
                "player_id": connection_id,
            },
        )
        while True:
            text = await websocket.receive_text()
            # try to parse JSON messages with structured events
            try:
                payload = json.loads(text)
            except Exception:
                await connection_manager.send_personal_message(
                    connection_id,
                    {
                        "event": "message",
                        "data": text,
                    },
                )
                continue

            # route input events to the game engine
            event = payload.get("event")
            if event in {"input", "attempt"}:
                await game_engine.process_input(connection_id, payload)
            elif event == "sync_state":
                room_id = payload.get("room_id")
                if not isinstance(room_id, str) or not room_id:
                    await connection_manager.send_personal_message(
                        connection_id,
                        {
                            "event": "error",
                            "message": "invalid_room_id",
                        },
                    )
                    continue

                room = await game_room_manager.get_room(room_id)
                if room is None:
                    await connection_manager.send_personal_message(
                        connection_id,
                        {
                            "event": "error",
                            "message": "room_not_found",
                        },
                    )
                    continue

                state = await game_engine.get_public_state(room)
                await connection_manager.send_personal_message(
                    connection_id,
                    {
                        "event": "game_state_sync",
                        "room_id": room.id,
                        "state_version": state.state_version,
                        "game_state": state.model_dump(mode="json"),
                    },
                )
            else:
                await connection_manager.send_personal_message(
                    connection_id,
                    {
                        "event": "message",
                        "data": payload,
                    },
                )
    except WebSocketDisconnect:
        pass
    finally:
        await lobby_manager.remove_player_from_all_lobbies(connection_id)
        await game_room_manager.remove_player_from_all_rooms(connection_id)
        await connection_manager.disconnect(connection_id)
