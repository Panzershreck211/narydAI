"""WebSocket-рассылка изменений нарядов (in-memory, один процесс).

Для нескольких воркеров uvicorn заменить на Redis pub/sub — интерфейс останется тем же.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.models.enums import Role

log = logging.getLogger(__name__)

STAFF_ROLES = {Role.MASTER, Role.MANAGER, Role.ADMIN}


class ConnectionManager:
    def __init__(self) -> None:
        self._by_user: dict[int, set[WebSocket]] = defaultdict(set)
        self._roles: dict[int, Role] = {}
        self._brigades: dict[int, int | None] = {}

    async def connect(self, ws: WebSocket, user_id: int, role: Role, brigade_id: int | None) -> None:
        await ws.accept()
        self._by_user[user_id].add(ws)
        self._roles[user_id] = role
        self._brigades[user_id] = brigade_id

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        conns = self._by_user.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._by_user.pop(user_id, None)
                self._roles.pop(user_id, None)
                self._brigades.pop(user_id, None)

    async def send_to_users(self, user_ids: set[int], message: dict[str, Any]) -> None:
        sockets = [ws for uid in user_ids for ws in self._by_user.get(uid, ())]
        if sockets:
            await asyncio.gather(*(self._safe_send(ws, message) for ws in sockets))

    async def broadcast_order(
        self, message: dict[str, Any], executor_id: int | None, brigade_id: int | None
    ) -> None:
        """Мастерам/руководству — всё; исполнителю — только его наряды (или наряды его бригады)."""
        targets = {
            uid
            for uid, role in self._roles.items()
            if role in STAFF_ROLES
            or uid == executor_id
            or (executor_id is None and brigade_id is not None and self._brigades.get(uid) == brigade_id)
        }
        await self.send_to_users(targets, message)

    @staticmethod
    async def _safe_send(ws: WebSocket, message: dict[str, Any]) -> None:
        try:
            await ws.send_json(message)
        except Exception:  # клиент отвалился — его уберёт обработчик ws
            log.debug("ws send failed", exc_info=True)


manager = ConnectionManager()
