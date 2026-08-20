from fastapi import APIRouter, Depends, WebSocket, status

from app.channels.base import SafeWebSocket, WebSocketSession
from app.routers.dependencies import Helpers, get_helpers

router = APIRouter()


@router.websocket("/channels")
async def websocket_channels(websocket: WebSocket, helpers: Helpers = Depends(get_helpers)):
    if not helpers.authentication.current_user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    safe_websocket = SafeWebSocket(websocket)
    context = {"helpers": helpers, "authentication": helpers.authentication}
    session = WebSocketSession(safe_websocket, helpers.authentication.current_user, context)
    await session.handle()
