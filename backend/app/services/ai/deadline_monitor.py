"""ИИ-контроль сроков.

Каждые N секунд:
  * прогнозирует длительность работ по истории (медиана по оборудованию → по цеху и типу
    работ → норматив) и предупреждает мастера о риске просрочки заранее;
  * за 30 минут до дедлайна напоминает исполнителю;
  * при просрочке уведомляет исполнителя и мастеров.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models import User, WorkOrder
from app.models.enums import OPEN_STATUSES, OrderAction, OrderStatus, OrderType
from app.services.ai.pipeline import staff_to_alert
from app.services.notifications import deliver_outbox, notify
from app.services.realtime import manager
from app.services.workflow import log_event

log = logging.getLogger(__name__)

DEFAULT_DURATION = {OrderType.EMERGENCY: timedelta(hours=2), OrderType.PLANNED: timedelta(hours=4)}
NOT_STARTED = {OrderStatus.ISSUED, OrderStatus.ACCEPTED, OrderStatus.QUEUED, OrderStatus.REJECTED}
MIN_SAMPLES = 3


class DurationModel:
    """Медианы фактической длительности работ по закрытым нарядам."""

    def __init__(self, rows: list[tuple[int | None, int, OrderType, timedelta]]) -> None:
        by_eq: dict[int, list[float]] = {}
        by_ws: dict[tuple[int, OrderType], list[float]] = {}
        for equipment_id, workshop_id, otype, spent in rows:
            sec = spent.total_seconds()
            if equipment_id:
                by_eq.setdefault(equipment_id, []).append(sec)
            by_ws.setdefault((workshop_id, otype), []).append(sec)
        self.by_eq = {k: median(v) for k, v in by_eq.items() if len(v) >= MIN_SAMPLES}
        self.by_ws = {k: median(v) for k, v in by_ws.items() if len(v) >= MIN_SAMPLES}

    def predict(self, order: WorkOrder) -> timedelta:
        if order.equipment_id in self.by_eq:
            return timedelta(seconds=self.by_eq[order.equipment_id])
        if (order.workshop_id, order.type) in self.by_ws:
            return timedelta(seconds=self.by_ws[(order.workshop_id, order.type)])
        return DEFAULT_DURATION[order.type]

    @classmethod
    async def load(cls, db: AsyncSession, days: int = 180) -> "DurationModel":
        since = utcnow() - timedelta(days=days)
        stmt = select(
            WorkOrder.equipment_id, WorkOrder.workshop_id, WorkOrder.type, WorkOrder.started_at, WorkOrder.completed_at
        ).where(
            WorkOrder.status == OrderStatus.CLOSED,
            WorkOrder.started_at.is_not(None),
            WorkOrder.completed_at.is_not(None),
            WorkOrder.closed_at >= since,
        )
        rows = [(eq, ws, t, done - start) for eq, ws, t, start, done in (await db.execute(stmt)).all()]
        return cls(rows)


async def check_deadlines(db: AsyncSession, now: datetime | None = None) -> int:
    """Один проход мониторинга. Возвращает число отправленных оповещений."""
    now = now or utcnow()
    orders = (
        await db.scalars(
            select(WorkOrder).where(
                WorkOrder.status.in_(OPEN_STATUSES),
                ~(WorkOrder.reminder_sent & WorkOrder.overdue_notified & WorkOrder.risk_notified),
            )
        )
    ).unique().all()
    if not orders:
        return 0

    model = await DurationModel.load(db)
    changed: dict[int, WorkOrder] = {}
    for order in orders:
        executor = await db.get(User, order.executor_id) if order.executor_id else None
        left = order.deadline - now

        if left <= timedelta(0) and not order.overdue_notified:
            order.overdue_notified = order.reminder_sent = order.risk_notified = True
            late = int(-left.total_seconds() // 60)
            log_event(db, order, None, OrderAction.OVERDUE, reason=f"Просрочен на {late} мин")
            await notify(
                db,
                [executor, *await staff_to_alert(db, order)],
                kind="overdue",
                title=f"Просрочен наряд {order.number}",
                body=f"{order.description[:120]} — срок истёк {order.deadline:%d.%m %H:%M} UTC",
                order=order,
                emergency=True,
            )
            changed[order.id] = order
            continue

        if timedelta(0) < left <= timedelta(minutes=settings.reminder_before_min) and not order.reminder_sent:
            order.reminder_sent = True
            log_event(db, order, None, OrderAction.REMINDER, reason=f"До срока {int(left.total_seconds() // 60)} мин")
            await notify(
                db,
                [executor] if executor else await staff_to_alert(db, order),
                kind="reminder",
                title=f"Через {int(left.total_seconds() // 60)} мин срок наряда {order.number}",
                body=order.description[:160],
                order=order,
            )
            changed[order.id] = order

        if not order.risk_notified:
            expected = model.predict(order)
            if order.status in NOT_STARTED:
                eta = now + expected
            elif order.started_at:
                eta = max(now, order.started_at + expected)
            else:
                eta = now
            if eta > order.deadline:
                order.risk_notified = True
                minutes = int(expected.total_seconds() // 60)
                reason = f"Прогноз длительности {minutes} мин, ожидаемое окончание {eta:%H:%M} UTC позже срока"
                log_event(db, order, None, OrderAction.RISK, reason=reason)
                await notify(
                    db,
                    await staff_to_alert(db, order),
                    kind="risk",
                    title=f"Риск просрочки: {order.number}",
                    body=reason,
                    order=order,
                    emergency=False,
                )
                changed[order.id] = order

    await db.commit()
    await deliver_outbox(db)
    for order in changed.values():
        await manager.broadcast_order(
            {"type": "order_changed", "order_id": order.id, "status": order.status.value},
            order.executor_id,
            order.brigade_id,
        )
    return len(changed)


async def run_forever(stop: asyncio.Event) -> None:
    log.info("AI deadline monitor started (every %ss)", settings.deadline_check_interval_sec)
    while not stop.is_set():
        try:
            async with SessionLocal() as db:
                await check_deadlines(db)
        except Exception:
            log.exception("deadline monitor tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.deadline_check_interval_sec)
        except TimeoutError:
            pass
