from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.connection_manager import connection_manager

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
        await connection_manager.disconnect(connection_id)
