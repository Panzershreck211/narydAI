"""Рейтинг исполнителей.

Баллы за каждый закрытый наряд = 10 × сложность × своевременность × качество.
  * сложность: приоритет × (1.5 для аварийных) × критичность оборудования;
  * своевременность: 1.0 в срок, далее −0.5 за каждые 24 ч опоздания (не ниже 0.3);
  * качество: среднее оценки мастера и ИИ-оценки, нормированное к 1.
Штраф −2 балла за каждый отклонённый наряд.
"""

from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReport, Equipment, OrderEvent, User, WorkOrder
from app.models.enums import (
    Criticality,
    OrderAction,
    OrderStatus,
    OrderType,
    Priority,
    Role,
)

PRIORITY_W = {Priority.LOW: 1.0, Priority.MEDIUM: 1.5, Priority.HIGH: 2.0, Priority.CRITICAL: 3.0}
CRIT_W = {Criticality.A: 1.5, Criticality.B: 1.2, Criticality.C: 1.0}
REJECT_PENALTY = 2.0


class RatingRow(BaseModel):
    rank: int
    executor_id: int
    fio: str
    specialty: str | None
    closed: int
    on_time_pct: float
    avg_quality: float | None
    rejects: int
    points: float


def complexity(otype: OrderType, priority: Priority, criticality: Criticality | None) -> float:
    w = PRIORITY_W[priority] * (1.5 if otype == OrderType.EMERGENCY else 1.0)
    return w * CRIT_W.get(criticality, 1.0) if criticality else w


def timeliness(completed_at: datetime, deadline: datetime) -> float:
    late_h = (completed_at - deadline).total_seconds() / 3600
    if late_h <= 0:
        return 1.0
    return max(0.3, 1.0 - 0.5 * late_h / 24)


async def compute_ratings(db: AsyncSession, since: datetime, until: datetime) -> list[RatingRow]:
    latest_ai = (
        select(AIReport.order_id, func.max(AIReport.id).label("rid")).group_by(AIReport.order_id).subquery()
    )
    stmt = (
        select(
            WorkOrder.executor_id,
            WorkOrder.type,
            WorkOrder.priority,
            WorkOrder.deadline,
            WorkOrder.completed_at,
            WorkOrder.master_score,
            Equipment.criticality,
            AIReport.score,
        )
        .outerjoin(Equipment, Equipment.id == WorkOrder.equipment_id)
        .outerjoin(latest_ai, latest_ai.c.order_id == WorkOrder.id)
        .outerjoin(AIReport, AIReport.id == latest_ai.c.rid)
        .where(
            WorkOrder.status == OrderStatus.CLOSED,
            WorkOrder.executor_id.is_not(None),
            WorkOrder.closed_at >= since,
            WorkOrder.closed_at < until,
        )
    )

    acc: dict[int, dict] = defaultdict(lambda: {"points": 0.0, "closed": 0, "on_time": 0, "q": []})
    for ex_id, otype, prio, deadline, done, m_score, crit, ai_score in (await db.execute(stmt)).all():
        scores = [s for s in (m_score, ai_score) if s is not None]
        quality = (sum(scores) / len(scores)) if scores else 3.0
        a = acc[ex_id]
        a["closed"] += 1
        a["on_time"] += done <= deadline
        a["q"].append(quality)
        a["points"] += 10 * complexity(otype, prio, crit) * timeliness(done, deadline) * (quality / 5)

    rejects = dict(
        (
            await db.execute(
                select(OrderEvent.user_id, func.count())
                .where(
                    OrderEvent.action == OrderAction.REJECT,
                    OrderEvent.timestamp >= since,
                    OrderEvent.timestamp < until,
                )
                .group_by(OrderEvent.user_id)
            )
        ).all()
    )

    executors = (await db.scalars(select(User).where(User.role == Role.EXECUTOR, User.is_active.is_(True)))).all()
    rows = []
    for u in executors:
        a = acc.get(u.id, {"points": 0.0, "closed": 0, "on_time": 0, "q": []})
        rej = rejects.get(u.id, 0)
        rows.append(
            RatingRow(
                rank=0,
                executor_id=u.id,
                fio=u.fio,
                specialty=u.specialty,
                closed=a["closed"],
                on_time_pct=round(100 * a["on_time"] / a["closed"], 1) if a["closed"] else 0.0,
                avg_quality=round(sum(a["q"]) / len(a["q"]), 2) if a["q"] else None,
                rejects=rej,
                points=round(max(0.0, a["points"] - REJECT_PENALTY * rej), 1),
            )
        )
    rows.sort(key=lambda r: (-r.points, -r.closed, r.fio))
    for i, r in enumerate(rows, 1):
        r.rank = i
    return rows
