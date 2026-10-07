from datetime import datetime

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import utcnow
from app.models import OrderEvent, User, WorkOrder
from app.models.enums import OPEN_STATUSES, OrderStatus, Role
from app.schemas.order import (
    AIReportOut,
    EventOut,
    MaterialOut,
    OrderDetail,
    OrderOut,
    PhotoOut,
)
from app.services.workflow import allowed_actions

DETAIL_OPTIONS = (
    selectinload(WorkOrder.events).joinedload(OrderEvent.user),
    selectinload(WorkOrder.photos),
    selectinload(WorkOrder.materials),
    selectinload(WorkOrder.ai_reports),
)


async def load_order(db: AsyncSession, order_id: int, *, detail: bool = True, lock: bool = False) -> WorkOrder | None:
    """lock=True — блокировка строки наряда до commit: двойное нажатие «Исполнено» или два
    члена бригады, одновременно взявшие наряд, обрабатываются строго по очереди."""
    stmt = select(WorkOrder).where(WorkOrder.id == order_id).execution_options(populate_existing=True)
    if lock:
        # of=WorkOrder: у наряда есть LEFT JOIN-связи, а FOR UPDATE на них PostgreSQL не допускает
        stmt = stmt.with_for_update(of=WorkOrder)
    if detail:
        stmt = stmt.options(*DETAIL_OPTIONS)
    return (await db.scalars(stmt)).unique().one_or_none()


def make_number(order: WorkOrder) -> str:
    return f"НР-{order.created_at:%Y}-{order.id:06d}"


def visible_to(stmt: Select, user: User) -> Select:
    """Исполнитель видит только свои наряды и невзятые наряды своей бригады."""
    if user.role != Role.EXECUTOR:
        return stmt
    own = WorkOrder.executor_id == user.id
    if user.brigade_id is None:
        return stmt.where(own)
    return stmt.where(or_(own, and_(WorkOrder.executor_id.is_(None), WorkOrder.brigade_id == user.brigade_id)))


def overdue_clause(now: datetime):
    return and_(WorkOrder.status.in_(OPEN_STATUSES), WorkOrder.deadline < now)


def to_out(order: WorkOrder, user: User, now: datetime | None = None) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.is_overdue = order.overdue_at(now or utcnow())
    out.allowed_actions = allowed_actions(order, user)
    return out


def to_detail(order: WorkOrder, user: User, media_url: str) -> OrderDetail:
    base = to_out(order, user).model_dump()
    latest_ai = order.ai_reports[-1] if order.ai_reports else None
    return OrderDetail(
        **base,
        work_report=order.work_report,
        fault_code=order.fault_code,
        events=[EventOut.model_validate(e) for e in order.events],
        photos=[
            PhotoOut(id=p.id, type=p.type, url=f"{media_url}/{p.file_path}", meta=p.meta, created_at=p.created_at)
            for p in order.photos
        ],
        materials=[MaterialOut.model_validate(m) for m in order.materials],
        ai_report=AIReportOut.model_validate(latest_ai) if latest_ai else None,
    )


# Колонки канбан-доски мастера. «Просроченные» — отдельная колонка поверх статусов.
BOARD_COLUMNS: list[tuple[str, str, set[OrderStatus]]] = [
    ("issued", "Выданные", {OrderStatus.ISSUED, OrderStatus.REJECTED}),
    ("accepted", "Принятые", {OrderStatus.ACCEPTED}),
    ("in_progress", "В работе", {OrderStatus.IN_PROGRESS, OrderStatus.PAUSED}),
    ("queued", "В очереди", {OrderStatus.QUEUED}),
    ("done", "Выполненные", {OrderStatus.COMPLETED, OrderStatus.CLOSED}),
]
