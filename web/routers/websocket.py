
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from web.core import manager, check_admin_auth


router = APIRouter()

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await check_admin_auth(websocket=websocket)
    await manager.connect(websocket)
    try:
        while True:
            # Maintain connection, wait for client close
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

