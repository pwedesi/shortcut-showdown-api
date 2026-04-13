from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time channel: connect, echo received text messages, clean disconnect."""
    await websocket.accept()
    await websocket.send_json(
        {
            "event": "connect",
            "message": "connected to Shortcut Showdown API",
        }
    )
    try:
        while True:
            text = await websocket.receive_text()
            await websocket.send_json(
                {
                    "event": "message",
                    "data": text,
                }
            )
    except WebSocketDisconnect:
        pass
