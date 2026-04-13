from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.connection_manager import connection_manager
from app.core.game_room_manager import game_room_manager
from app.core.lobby_manager import lobby_manager

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
            await connection_manager.send_personal_message(
                connection_id,
                {
                    "event": "message",
                    "data": text,
                },
            )
    except WebSocketDisconnect:
        pass
    finally:
        await lobby_manager.remove_player_from_all_lobbies(connection_id)
        await game_room_manager.remove_player_from_all_rooms(connection_id)
        await connection_manager.disconnect(connection_id)
