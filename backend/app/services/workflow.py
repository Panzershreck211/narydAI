"""Машина состояний наряда: кто, из какого статуса и куда может перевести наряд."""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import OrderEvent, User, WorkOrder
from app.models.enums import FINAL_STATUSES, OrderAction, OrderStatus, OrderType, Role

S = OrderStatus
EXECUTOR = frozenset({Role.EXECUTOR})
MASTER = frozenset({Role.MASTER, Role.ADMIN})


@dataclass(frozen=True)
class Transition:
    sources: frozenset[OrderStatus]
    target: OrderStatus
    roles: frozenset[Role]
    reason_required: bool = False


TRANSITIONS: dict[OrderAction, Transition] = {
    OrderAction.ACCEPT: Transition(frozenset({S.ISSUED}), S.ACCEPTED, EXECUTOR),
    OrderAction.QUEUE: Transition(frozenset({S.ISSUED, S.ACCEPTED}), S.QUEUED, EXECUTOR),
    OrderAction.REJECT: Transition(frozenset({S.ISSUED, S.ACCEPTED, S.QUEUED}), S.REJECTED, EXECUTOR, True),
    OrderAction.START: Transition(frozenset({S.ISSUED, S.ACCEPTED, S.QUEUED, S.PAUSED}), S.IN_PROGRESS, EXECUTOR),
    OrderAction.PAUSE: Transition(frozenset({S.IN_PROGRESS}), S.PAUSED, EXECUTOR, True),
    OrderAction.COMPLETE: Transition(frozenset({S.IN_PROGRESS}), S.COMPLETED, EXECUTOR),
    OrderAction.APPROVE: Transition(frozenset({S.COMPLETED}), S.CLOSED, MASTER),
    OrderAction.RETURN: Transition(frozenset({S.COMPLETED}), S.IN_PROGRESS, MASTER, True),
    OrderAction.REASSIGN: Transition(
        frozenset({S.ISSUED, S.ACCEPTED, S.QUEUED, S.PAUSED, S.REJECTED}), S.ISSUED, MASTER
    ),
    OrderAction.CANCEL: Transition(frozenset(set(S) - FINAL_STATUSES), S.CANCELLED, MASTER, True),
}

# Действия, которые идут через общий эндпоинт /actions/{action} (без доп. полей)
SIMPLE_ACTIONS = {
    OrderAction.ACCEPT,
    OrderAction.QUEUE,
    OrderAction.REJECT,
    OrderAction.START,
    OrderAction.PAUSE,
    OrderAction.RETURN,
    OrderAction.CANCEL,
}


def can_view(order: WorkOrder, user: User) -> bool:
    if user.role != Role.EXECUTOR:
        return True
    return is_assignee(order, user)


def is_assignee(order: WorkOrder, user: User) -> bool:
    if order.executor_id is not None:
        return order.executor_id == user.id
    # Наряд выдан на бригаду и ещё никем не взят
    return order.brigade_id is not None and order.brigade_id == user.brigade_id


def allowed_actions(order: WorkOrder, user: User) -> list[str]:
    result = []
    for action, tr in TRANSITIONS.items():
        if order.status not in tr.sources or user.role not in tr.roles:
            continue
        if user.role == Role.EXECUTOR and not is_assignee(order, user):
            continue
        result.append(action.value)
    return result


def log_event(
    db: AsyncSession,
    order: WorkOrder,
    user: User | None,
    action: OrderAction,
    *,
    from_status: OrderStatus | None = None,
    to_status: OrderStatus | None = None,
    reason: str | None = None,
) -> OrderEvent:
    event = OrderEvent(
        order_id=order.id,
        user_id=user.id if user else None,
        action=action,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
    )
    db.add(event)
    return event


async def apply_transition(
    db: AsyncSession, order: WorkOrder, user: User, action: OrderAction, reason: str | None = None
) -> OrderStatus:
    """Проверяет права и переход, меняет статус и пишет событие. Возвращает прежний статус."""
    tr = TRANSITIONS.get(action)
    if tr is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Неизвестное действие: {action}")
    if user.role not in tr.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Действие недоступно для вашей роли")
    if user.role == Role.EXECUTOR and not is_assignee(order, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Наряд назначен другому исполнителю")
    if order.status not in tr.sources:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Нельзя выполнить «{action.value}» из статуса «{order.status.value}»",
        )
    reason = (reason or "").strip() or None
    if tr.reason_required and not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите причину")

    if action == OrderAction.START:
        await _ensure_single_active(db, order, user)

    now = utcnow()
    prev = order.status
    order.status = tr.target

    # Наряд на бригаду: первый, кто взял, становится исполнителем
    if user.role == Role.EXECUTOR and order.executor_id is None and action != OrderAction.REJECT:
        order.executor_id = user.id
    if action == OrderAction.START and order.started_at is None:
        order.started_at = now
    elif action == OrderAction.COMPLETE:
        order.completed_at = now
    elif action == OrderAction.APPROVE:
        order.closed_at = now
    elif action == OrderAction.RETURN:
        order.completed_at = None

    log_event(db, order, user, action, from_status=prev, to_status=tr.target, reason=reason)
    return prev


async def _ensure_single_active(db: AsyncSession, order: WorkOrder, user: User) -> None:
    """У исполнителя одновременно один наряд в работе. Аварийный наряд автоматически
    ставит текущий плановый на паузу, плановый — получает 409."""
    active = (
        await db.scalars(
            select(WorkOrder).where(
                WorkOrder.executor_id == user.id,
                WorkOrder.status == OrderStatus.IN_PROGRESS,
                WorkOrder.id != order.id,
            )
        )
    ).all()
    if not active:
        return
    if order.type != OrderType.EMERGENCY:
        numbers = ", ".join(o.number or str(o.id) for o in active)
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Сначала приостановите или завершите наряд {numbers}"
        )
    for other in active:
        other.status = OrderStatus.PAUSED
        log_event(
            db,
            other,
            user,
            OrderAction.PAUSE,
            from_status=OrderStatus.IN_PROGRESS,
            to_status=OrderStatus.PAUSED,
            reason=f"Переключение на аварийный наряд {order.number}",
        )
