from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func, select

from app.core.config import settings
from app.core.deps import DB, AnalyticsUser, StaffUser
from app.db.base import utcnow
from app.models import Equipment, WorkOrder
from app.models.enums import OPEN_STATUSES, OrderStatus
from app.schemas.order import ShiftCounters
from app.services.ai.rating import RatingRow, compute_ratings
from app.services.orders import overdue_clause

router = APIRouter(tags=["dashboard & analytics"])


def current_shift_start(now: datetime) -> datetime:
    tz = timezone(timedelta(hours=settings.plant_utc_offset_hours))
    local = now.astimezone(tz)
    day_start = local.replace(hour=settings.day_shift_start_hour, minute=0, second=0, microsecond=0)
    night_start = day_start + timedelta(hours=12)
    if local >= night_start:
        start = night_start
    elif local >= day_start:
        start = day_start
    else:
        start = night_start - timedelta(days=1)
    return start.astimezone(UTC)


@router.get("/dashboard/counters", response_model=ShiftCounters, summary="Счётчики текущей смены")
async def counters(db: DB, _: StaffUser, workshop_id: int | None = None, since: datetime | None = None):
    now = utcnow()
    since = since or current_shift_start(now)

    def scoped(stmt):
        return stmt.where(WorkOrder.workshop_id == workshop_id) if workshop_id else stmt

    count = func.count(WorkOrder.id)
    issued = await db.scalar(scoped(select(count).where(WorkOrder.created_at >= since)))
    completed = await db.scalar(scoped(select(count).where(WorkOrder.completed_at >= since)))
    overdue = await db.scalar(scoped(select(count).where(overdue_clause(now))))
    in_progress = await db.scalar(scoped(select(count).where(WorkOrder.status == OrderStatus.IN_PROGRESS)))
    down = await db.scalar(
        scoped(
            select(func.count(distinct(WorkOrder.equipment_id))).where(
                WorkOrder.equipment_stopped.is_(True),
                WorkOrder.equipment_id.is_not(None),
                WorkOrder.status.in_(OPEN_STATUSES | {OrderStatus.COMPLETED}),
            )
        )
    )
    return ShiftCounters(issued=issued, completed=completed, overdue=overdue, equipment_down=down, in_progress=in_progress)


@router.get("/analytics/ratings", response_model=list[RatingRow], summary="Рейтинг исполнителей")
async def ratings(
    db: DB,
    _: AnalyticsUser,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    now = utcnow()
    return await compute_ratings(db, date_from or now - timedelta(days=30), date_to or now + timedelta(seconds=1))


class DowntimeRow(BaseModel):
    equipment_id: int
    equipment: str
    inventory_number: str
    orders: int
    downtime_hours: float
    still_down: bool


@router.get("/analytics/downtime", response_model=list[DowntimeRow], summary="Простои оборудования")
async def downtime(db: DB, _: AnalyticsUser, days: int = Query(default=30, le=365)):
    now = utcnow()
    since = now - timedelta(days=days)
    stmt = (
        select(WorkOrder, Equipment)
        .join(Equipment, Equipment.id == WorkOrder.equipment_id)
        .where(WorkOrder.equipment_stopped.is_(True), WorkOrder.created_at >= since)
    )
    acc: dict[int, DowntimeRow] = {}
    for order, eq in (await db.execute(stmt)).unique().all():
        end = order.completed_at or (now if order.status != OrderStatus.CANCELLED else order.created_at)
        row = acc.setdefault(
            eq.id,
            DowntimeRow(
                equipment_id=eq.id,
                equipment=eq.name,
                inventory_number=eq.inventory_number,
                orders=0,
                downtime_hours=0.0,
                still_down=False,
            ),
        )
        row.orders += 1
        row.downtime_hours = round(row.downtime_hours + (end - order.created_at).total_seconds() / 3600, 2)
        row.still_down |= order.completed_at is None and order.status in OPEN_STATUSES
    return sorted(acc.values(), key=lambda r: -r.downtime_hours)
