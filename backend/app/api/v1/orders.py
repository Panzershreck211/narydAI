import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser, ExecutorUser, MasterUser, StaffUser
from app.db.base import utcnow
from app.models import (
    Brigade,
    Equipment,
    FaultCode,
    Material,
    OrderMaterial,
    OrderPhoto,
    User,
    WorkOrder,
    Workshop,
)
from app.models.enums import (
    OrderAction,
    OrderStatus,
    OrderType,
    PhotoType,
    Priority,
    Role,
)
from app.schemas.order import (
    ApproveIn,
    BoardColumn,
    CompleteIn,
    OrderCreate,
    OrderDetail,
    OrderOut,
    OrderUpdate,
    ReasonIn,
    ReassignIn,
)
from app.services.ai.photo_checker import analyze_photo
from app.services.ai.pipeline import VERDICT_RU, run_llm_enrichment, run_rules_check
from app.services.notifications import deliver_outbox, notify
from app.services.orders import (
    BOARD_COLUMNS,
    load_order,
    make_number,
    overdue_clause,
    to_detail,
    to_out,
    visible_to,
)
from app.services.realtime import manager
from app.services.workflow import (
    SIMPLE_ACTIONS,
    apply_transition,
    can_view,
    is_assignee,
    log_event,
)

router = APIRouter(prefix="/orders", tags=["work orders"])

MEDIA_URL = "/media"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PRIORITY_RU = {Priority.LOW: "низкий", Priority.MEDIUM: "средний", Priority.HIGH: "высокий", Priority.CRITICAL: "критический"}


# ---------- helpers ----------


async def _get_visible(db: DB, order_id: int, user: User) -> WorkOrder:
    order = await load_order(db, order_id)
    if order is None or not can_view(order, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Наряд не найден")
    return order


async def _finish(db: DB, order: WorkOrder, user: User, action: OrderAction) -> OrderDetail:
    await db.commit()
    await deliver_outbox(db)
    await manager.broadcast_order(
        {"type": "order_changed", "order_id": order.id, "status": order.status.value, "action": action.value},
        order.executor_id,
        order.brigade_id,
    )
    fresh = await load_order(db, order.id)
    return to_detail(fresh, user, MEDIA_URL)


async def _validate_assignee(db: DB, executor_id: int | None, brigade_id: int | None) -> User | None:
    executor = None
    if executor_id is not None:
        executor = await db.get(User, executor_id)
        if executor is None or executor.role != Role.EXECUTOR or not executor.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Исполнитель не найден")
    if brigade_id is not None and await db.get(Brigade, brigade_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Бригада не найдена")
    return executor


async def _assignees(db: DB, order: WorkOrder) -> list[User]:
    if order.executor_id:
        return [await db.get(User, order.executor_id)]
    if order.brigade_id:
        return list(
            await db.scalars(
                select(User).where(
                    User.brigade_id == order.brigade_id, User.role == Role.EXECUTOR, User.is_active.is_(True)
                )
            )
        )
    return []


async def _notify_new_order(db: DB, order: WorkOrder) -> None:
    emergency = order.type == OrderType.EMERGENCY
    await notify(
        db,
        await _assignees(db, order),
        kind="new_order",
        title=("🔴 АВАРИЙНЫЙ наряд " if emergency else "Новый наряд ") + (order.number or ""),
        body=f"{order.description[:140]} · приоритет {PRIORITY_RU[order.priority]} · срок {order.deadline:%d.%m %H:%M} UTC",
        order=order,
    )


# ---------- CRUD ----------


@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED, summary="Выдать наряд")
async def create_order(body: OrderCreate, db: DB, master: MasterUser):
    if await db.get(Workshop, body.workshop_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Участок не найден")
    if body.equipment_id is not None:
        eq = await db.get(Equipment, body.equipment_id)
        if eq is None or eq.workshop_id != body.workshop_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Оборудование не найдено на этом участке")
    if body.deadline <= utcnow():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Срок исполнения должен быть в будущем")
    await _validate_assignee(db, body.executor_id, body.brigade_id)

    order = WorkOrder(**body.model_dump(), master_id=master.id, status=OrderStatus.ISSUED)
    db.add(order)
    await db.flush()
    order.number = make_number(order)
    log_event(db, order, master, OrderAction.CREATE, to_status=OrderStatus.ISSUED)
    await _notify_new_order(db, order)
    return await _finish(db, order, master, OrderAction.CREATE)


@router.get("", response_model=list[OrderOut], summary="Список нарядов (исполнитель видит только свои)")
async def list_orders(
    db: DB,
    user: CurrentUser,
    status_: list[OrderStatus] | None = Query(default=None, alias="status"),
    type_: OrderType | None = Query(default=None, alias="type"),
    workshop_id: int | None = None,
    executor_id: int | None = None,
    overdue: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    now = utcnow()
    stmt = visible_to(select(WorkOrder), user)
    if status_:
        stmt = stmt.where(WorkOrder.status.in_(status_))
    if type_:
        stmt = stmt.where(WorkOrder.type == type_)
    if workshop_id:
        stmt = stmt.where(WorkOrder.workshop_id == workshop_id)
    if executor_id:
        stmt = stmt.where(WorkOrder.executor_id == executor_id)
    if overdue is True:
        stmt = stmt.where(overdue_clause(now))
    elif overdue is False:
        stmt = stmt.where(~overdue_clause(now))
    if created_from:
        stmt = stmt.where(WorkOrder.created_at >= created_from)
    if created_to:
        stmt = stmt.where(WorkOrder.created_at < created_to)
    # Аварийные — первыми, затем по сроку
    stmt = stmt.order_by((WorkOrder.type == OrderType.EMERGENCY).desc(), WorkOrder.deadline).limit(limit).offset(offset)
    return [to_out(o, user, now) for o in (await db.scalars(stmt)).unique()]


@router.get("/board", response_model=list[BoardColumn], summary="Канбан-доска мастера")
async def board(db: DB, user: StaffUser, workshop_id: int | None = None, hours: int = Query(default=24, le=24 * 31)):
    now = utcnow()
    since = now - timedelta(hours=hours)
    stmt = select(WorkOrder).where(
        WorkOrder.status != OrderStatus.CANCELLED,
        # открытые — всегда, закрытые — только за период
        (WorkOrder.status != OrderStatus.CLOSED) | (WorkOrder.closed_at >= since),
    )
    if workshop_id:
        stmt = stmt.where(WorkOrder.workshop_id == workshop_id)
    orders = [to_out(o, user, now) for o in (await db.scalars(stmt.order_by(WorkOrder.deadline))).unique()]

    columns = [
        BoardColumn(key=key, title=title, orders=[o for o in orders if o.status in statuses and not o.is_overdue])
        for key, title, statuses in BOARD_COLUMNS
    ]
    columns.append(BoardColumn(key="overdue", title="Просроченные", orders=[o for o in orders if o.is_overdue]))
    return columns


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(order_id: int, db: DB, user: CurrentUser):
    return to_detail(await _get_visible(db, order_id, user), user, MEDIA_URL)


@router.patch("/{order_id}", response_model=OrderDetail, summary="Изменить наряд (мастер)")
async def update_order(order_id: int, body: OrderUpdate, db: DB, master: MasterUser):
    order = await _get_visible(db, order_id, master)
    if order.status in (OrderStatus.CLOSED, OrderStatus.CANCELLED, OrderStatus.COMPLETED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Наряд уже исполнен или закрыт")
    data = body.model_dump(exclude_unset=True)
    if "equipment_id" in data and data["equipment_id"] is not None:
        eq = await db.get(Equipment, data["equipment_id"])
        if eq is None or eq.workshop_id != order.workshop_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Оборудование не найдено на этом участке")
    if "deadline" in data:
        if data["deadline"] is None or data["deadline"].tzinfo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "deadline должен содержать часовой пояс")
        order.reminder_sent = order.overdue_notified = order.risk_notified = False
    for k, v in data.items():
        setattr(order, k, v)
    log_event(db, order, master, OrderAction.UPDATE, reason=", ".join(data))
    return await _finish(db, order, master, OrderAction.UPDATE)


# ---------- фото ----------


@router.post("/{order_id}/photos", response_model=OrderDetail, summary="Прикрепить фото (до 5 на тип)")
async def upload_photos(
    order_id: int,
    db: DB,
    user: CurrentUser,
    type: PhotoType = Query(...),
    files: list[UploadFile] = File(...),
):
    order = await _get_visible(db, order_id, user)
    if user.role == Role.EXECUTOR and not is_assignee(order, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Наряд назначен другому исполнителю")
    if user.role == Role.MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    if order.status in (OrderStatus.CLOSED, OrderStatus.CANCELLED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Наряд закрыт")

    existing = sum(1 for p in order.photos if p.type == type)
    if existing + len(files) > settings.max_photos_per_type:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Не больше {settings.max_photos_per_type} фото типа «{type.value}»"
        )

    folder = settings.media_dir / "orders" / str(order.id)
    folder.mkdir(parents=True, exist_ok=True)
    limit = settings.max_photo_mb * 1024 * 1024
    for f in files:
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{f.filename}: допустимы JPEG/PNG/WebP")
        data = await f.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{f.filename}: больше {settings.max_photo_mb} МБ")
        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[f.content_type]
        path = folder / f"{type.value}_{uuid.uuid4().hex}.{ext}"
        path.write_bytes(data)
        try:
            with Image.open(path) as img:
                img.verify()
            meta = await asyncio.to_thread(analyze_photo, path)
        except (UnidentifiedImageError, OSError, SyntaxError):
            path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{f.filename}: файл не является изображением") from None
        rel = path.relative_to(settings.media_dir).as_posix()
        db.add(OrderPhoto(order_id=order.id, type=type, file_path=rel, uploaded_by=user.id, meta=meta))

    log_event(db, order, user, OrderAction.PHOTO, reason=f"{'«до»' if type == PhotoType.BEFORE else '«после»'}: {len(files)} шт.")
    return await _finish(db, order, user, OrderAction.PHOTO)


# ---------- жизненный цикл ----------


@router.post(
    "/{order_id}/actions/{action}",
    response_model=OrderDetail,
    summary="Сменить статус: accept | queue | reject | start | pause | return | cancel",
)
async def order_action(order_id: int, action: OrderAction, db: DB, user: CurrentUser, body: ReasonIn | None = None):
    if action not in SIMPLE_ACTIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Используйте отдельный эндпоинт для этого действия")
    order = await _get_visible(db, order_id, user)
    reason = body.reason if body else None
    executor_before = order.executor_id
    await apply_transition(db, order, user, action, reason)

    master = await db.get(User, order.master_id)
    if action == OrderAction.REJECT:
        await notify(
            db,
            [master],
            kind="status",
            title=f"Наряд {order.number} отклонён",
            body=f"{user.fio}: {reason}",
            order=order,
        )
    elif action in (OrderAction.RETURN, OrderAction.CANCEL) and executor_before:
        verb = "возвращён на доработку" if action == OrderAction.RETURN else "отменён"
        await notify(
            db,
            [await db.get(User, executor_before)],
            kind="status",
            title=f"Наряд {order.number} {verb}",
            body=reason or "",
            order=order,
        )
    return await _finish(db, order, user, action)


@router.post("/{order_id}/complete", response_model=OrderDetail, summary="Исполнено: форма закрытия наряда")
async def complete_order(order_id: int, body: CompleteIn, db: DB, user: ExecutorUser, background: BackgroundTasks):
    order = await _get_visible(db, order_id, user)

    fault = await db.get(FaultCode, body.fault_code_id)
    if fault is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Шифр неисправности не найден")
    if order.type == OrderType.EMERGENCY and not any(p.type == PhotoType.AFTER for p in order.photos):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Для внепланового наряда обязательно фото «после» — загрузите его"
        )

    materials = []
    for m in body.materials:
        ref = await db.get(Material, m.material_id) if m.material_id else None
        if m.material_id and ref is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Материал id={m.material_id} не найден")
        materials.append(
            OrderMaterial(
                material_id=m.material_id,
                material_name=ref.name if ref else m.material_name,
                quantity=m.quantity,
                unit=(ref.unit if ref else m.unit) or "шт",
            )
        )

    await apply_transition(db, order, user, OrderAction.COMPLETE)
    order.work_report = body.work_report.strip()
    order.fault_code_id = fault.id
    order.fault_code = fault
    order.materials.extend(materials)
    await db.flush()

    report = await run_rules_check(db, order)
    master = await db.get(User, order.master_id)
    await notify(
        db,
        [master],
        kind="status",
        title=f"Наряд {order.number} исполнен — ждёт приёмки",
        body=f"{user.fio}. ИИ-проверка: {VERDICT_RU[report.verdict]} ({report.score:.1f}/5)",
        order=order,
        emergency=False,
    )
    result = await _finish(db, order, user, OrderAction.COMPLETE)
    background.add_task(run_llm_enrichment, order.id)
    return result


@router.post("/{order_id}/approve", response_model=OrderDetail, summary="Приёмка работ мастером")
async def approve_order(order_id: int, body: ApproveIn, db: DB, master: MasterUser):
    order = await _get_visible(db, order_id, master)
    await apply_transition(db, order, master, OrderAction.APPROVE, body.comment)
    order.master_score = body.master_score
    return await _finish(db, order, master, OrderAction.APPROVE)


@router.post("/{order_id}/reassign", response_model=OrderDetail, summary="Переназначить исполнителя/бригаду")
async def reassign_order(order_id: int, body: ReassignIn, db: DB, master: MasterUser):
    if body.executor_id is None and body.brigade_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите исполнителя или бригаду")
    order = await _get_visible(db, order_id, master)
    await _validate_assignee(db, body.executor_id, body.brigade_id)
    await apply_transition(db, order, master, OrderAction.REASSIGN, body.reason)
    order.executor_id = body.executor_id
    order.brigade_id = body.brigade_id
    order.started_at = None
    if body.deadline:
        if body.deadline.tzinfo is None or body.deadline <= utcnow():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Некорректный срок")
        order.deadline = body.deadline
        order.reminder_sent = order.overdue_notified = order.risk_notified = False
    await db.flush()
    await _notify_new_order(db, order)
    return await _finish(db, order, master, OrderAction.REASSIGN)


@router.post("/{order_id}/ai-check", response_model=OrderDetail, summary="Перезапустить ИИ-проверку")
async def rerun_ai_check(order_id: int, db: DB, user: StaffUser, background: BackgroundTasks):
    order = await _get_visible(db, order_id, user)
    if order.status not in (OrderStatus.COMPLETED, OrderStatus.CLOSED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Проверка доступна после исполнения наряда")
    await run_rules_check(db, order)
    result = await _finish(db, order, user, OrderAction.AI_CHECK)
    background.add_task(run_llm_enrichment, order.id)
    return result

