from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WorkOrder
from app.models.enums import Availability, OrderStatus, Role
from app.schemas.user import ExecutorAvailability

ACTIVE = (OrderStatus.IN_PROGRESS,)
WAITING = (OrderStatus.ISSUED, OrderStatus.ACCEPTED, OrderStatus.QUEUED, OrderStatus.PAUSED)


def classify(on_shift: bool, active: int, waiting: int) -> Availability:
    if not on_shift:
        return Availability.OFF_SHIFT
    if active and waiting:
        return Availability.QUEUED
    if active:
        return Availability.BUSY
    if waiting:
        return Availability.QUEUED
    return Availability.FREE


async def executors_availability(
    db: AsyncSession, brigade_id: int | None = None
) -> list[ExecutorAvailability]:
    active_cnt = func.count(case((WorkOrder.status.in_(ACTIVE), 1)))
    waiting_cnt = func.count(case((WorkOrder.status.in_(WAITING), 1)))
    stmt = (
        select(User, active_cnt, waiting_cnt)
        .outerjoin(WorkOrder, WorkOrder.executor_id == User.id)
        .where(User.role == Role.EXECUTOR, User.is_active.is_(True))
        .group_by(User.id)
        .order_by(User.fio)
    )
    if brigade_id is not None:
        stmt = stmt.where(User.brigade_id == brigade_id)

    rows = (await db.execute(stmt)).all()
    return [
        ExecutorAvailability(
            id=u.id,
            fio=u.fio,
            specialty=u.specialty,
            grade=u.grade,
            brigade_id=u.brigade_id,
            availability=classify(u.on_shift, active, waiting),
            active_orders=active,
            queued_orders=waiting,
        )
        for u, active, waiting in rows
    ]
