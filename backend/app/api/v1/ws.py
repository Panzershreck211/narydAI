from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.core.deps import user_from_token
from app.db.session import SessionLocal
from app.services.realtime import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    """Поток событий: order_changed / notification. Токен — access JWT в query (?token=...)."""
    async with SessionLocal() as db:
        try:
            user = await user_from_token(db, token)
        except HTTPException:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(ws, user.id, user.role, user.brigade_id)
    try:
        while True:
            msg = await ws.receive_text()  # клиент шлёт "ping" для keep-alive
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws, user.id)
