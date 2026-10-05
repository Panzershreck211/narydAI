from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User, WorkOrder
from app.models.enums import OrderType
from app.services.push import push_sender
from app.services.realtime import manager

OUTBOX = "notification_outbox"


async def notify(
    db: AsyncSession,
    users: Iterable[User | None],
    *,
    kind: str,
    title: str,
    body: str,
    order: WorkOrder | None = None,
    emergency: bool | None = None,
) -> None:
    """Сохраняет уведомления в БД и ставит доставку (WebSocket + push) в outbox сессии.

    Доставка выполняется в deliver_outbox() после commit — клиент не получит
    уведомление о данных, которых ещё нет в БД.
    """
    if emergency is None:
        emergency = order is not None and order.type == OrderType.EMERGENCY

    unique = {u.id: u for u in users if u is not None}
    rows = []
    for user in unique.values():
        row = Notification(
            user_id=user.id,
            order_id=order.id if order else None,
            kind=kind,
            title=title,
            body=body,
            is_emergency=emergency,
        )
        db.add(row)
        rows.append((user, row))
    await db.flush()

    outbox = db.info.setdefault(OUTBOX, [])
    for user, row in rows:
        outbox.append(
            {
                "user_id": user.id,
                "fcm_token": user.fcm_token,
                "notification": {
                    "id": row.id,
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "order_id": row.order_id,
                    "is_emergency": emergency,
                },
            }
        )


async def deliver_outbox(db: AsyncSession) -> None:
    """Вызывать после успешного commit."""
    outbox = db.info.pop(OUTBOX, [])
    for item in outbox:
        n = item["notification"]
        await manager.send_to_users({item["user_id"]}, {"type": "notification", "notification": n})
        await push_sender.send(
            item["fcm_token"],
            n["title"],
            n["body"],
            {"kind": n["kind"], "order_id": str(n["order_id"] or "")},
            n["is_emergency"],
        )


def discard_outbox(db: AsyncSession) -> None:
    db.info.pop(OUTBOX, None)
