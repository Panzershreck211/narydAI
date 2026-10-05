"""ИИ-помощник НарядAI: чат на Claude с инструментами для чтения данных системы.

Инструменты только читают и всегда учитывают роль: исполнитель видит лишь свои
наряды, аналитика доступна мастеру, руководителю и администратору. Ответ
стримится в браузер событиями (см. ChatEvent).
"""

import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.models import Equipment, FaultCode, Material, User, WorkOrder, Workshop
from app.models.enums import OPEN_STATUSES, OrderStatus, OrderType, Role
from app.services.availability import executors_availability
from app.services.orders import load_order, overdue_clause, visible_to

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
STAFF = {Role.MASTER, Role.MANAGER, Role.ADMIN}

STATUS_RU = {
    "issued": "выдан",
    "accepted": "принят",
    "queued": "в очереди",
    "in_progress": "в работе",
    "paused": "приостановлен",
    "completed": "исполнен, ждёт приёмки",
    "closed": "закрыт",
    "rejected": "отклонён",
    "cancelled": "отменён",
}

GUIDE = """\
Как устроена система НарядAI (отвечай по этим правилам, не выдумывай функций):
- Роли: мастер смены выдаёт и принимает наряды; исполнитель (слесарь, электрик…) работает в мобильном
  приложении; руководитель смотрит аналитику; администратор ведёт сотрудников и справочники.
- Первый запуск: если администратора нет, панель сама показывает экран «Добро пожаловать» для его создания.
- Регистрация сотрудника, в том числе нового администратора: войти администратором → «Сотрудники» →
  «+ Зарегистрировать» → ФИО, логин (латиница), пароль от 8 символов, роль; для рабочих — ПИН из 4–6 цифр.
- Справочники (участки, оборудование, бригады, шифры неисправностей, материалы): администратор →
  «Справочники» → вкладка → «+ Добавить».
- Выдать наряд: мастер → «Доска нарядов» → «+ Выдать наряд». Аварийный тип сам ставит критический приоритет,
  срок +2 ч и отметку «оборудование остановлено». Исполнители в списке отсортированы по занятости:
  зелёный — свободен, жёлтый — в работе, синий — есть очередь, серый — не на смене.
- Статусы: выдан → принят / в очереди → в работе (можно приостановить с причиной) → исполнен → закрыт
  мастером с оценкой 1–5. Мастер может вернуть на доработку, переназначить или отменить (с причиной).
- Закрытие в приложении: «Исполнено» → описание работ (можно голосом), шифр неисправности, материалы;
  для аварийных обязательно фото «после». ИИ-проверка ставит оценку и замечания, мастер видит их в карточке.
- ИИ-контроль сроков: напоминание исполнителю за 30 минут, уведомление о просрочке, ранний «риск просрочки»
  мастеру по средней длительности прошлых работ на этом оборудовании.
- Рейтинг: сложность × своевременность × качество (оценка мастера и ИИ), минус 2 балла за отказ.
- Ключ ИИ-помощника задаёт администратор в «Настройках»."""


def system_prompt(user: User, now: datetime) -> str:
    return (
        "Ты — ИИ-помощник системы НарядAI на горно-обогатительном предприятии АО «Костанайские минералы». "
        "Помогаешь мастерам, исполнителям, руководителям и администраторам: отвечаешь на вопросы о нарядах, "
        "сменах, исполнителях, простоях и о том, как пользоваться системой.\n\n"
        "Правила:\n"
        "- Отвечай по-русски, коротко и по делу; списки — маркерами. Номера нарядов пиши полностью (НР-2026-000012).\n"
        "- Данные о нарядах, людях и оборудовании бери только из инструментов. Если данных нет — так и скажи.\n"
        "- Ты только читаешь данные: ничего не создаёшь и не меняешь. Если просят выдать, закрыть или "
        "отменить наряд — объясни, где это сделать в панели или приложении.\n"
        "- По технике безопасности и допускам отсылай к инструкциям предприятия, не давай опасных советов.\n\n"
        f"{GUIDE}\n\n"
        f"Собеседник: {user.fio}, роль — {user.role.value}. Сейчас {now:%d.%m.%Y %H:%M} UTC."
    )


# ---------- инструменты ----------


class FindOrdersIn(BaseModel):
    status: list[Literal[tuple(STATUS_RU)]] | None = None  # type: ignore[valid-type]
    overdue: bool | None = None
    emergency_only: bool = False
    executor_name: str | None = Field(default=None, max_length=100)
    text: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=15, ge=1, le=30)


class OrderDetailsIn(BaseModel):
    number: str = Field(min_length=3, max_length=30)


class DaysIn(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class LookupIn(BaseModel):
    kind: Literal["fault_codes", "materials", "workshops", "equipment"]
    query: str | None = Field(default=None, max_length=100)


class EmptyIn(BaseModel):
    pass


def _schema(model: type[BaseModel]) -> dict:
    s = model.model_json_schema()
    s.pop("title", None)
    return s


TOOLS: list[dict[str, Any]] = [
    {
        "name": "shift_summary",
        "description": "Счётчики текущей смены: выдано, в работе, выполнено, просрочено, единиц оборудования в простое.",
        "input_schema": _schema(EmptyIn),
    },
    {
        "name": "find_orders",
        "description": (
            "Поиск нарядов. Фильтры: статусы (issued, accepted, queued, in_progress, paused, completed, closed, "
            "rejected, cancelled), только просроченные, только аварийные, часть ФИО исполнителя, текст в описании. "
            "Без фильтров — открытые наряды. Аварийные первыми, затем по сроку."
        ),
        "input_schema": _schema(FindOrdersIn),
    },
    {
        "name": "order_details",
        "description": "Подробности наряда по номеру (НР-2026-000012 или просто 12): история, отчёт, материалы, ИИ-проверка.",
        "input_schema": _schema(OrderDetailsIn),
    },
    {
        "name": "executors_status",
        "description": "Исполнители и их занятость сейчас: свободен / в работе / есть очередь / не на смене.",
        "input_schema": _schema(EmptyIn),
    },
    {
        "name": "executor_ratings",
        "description": "Рейтинг исполнителей за последние N дней: закрыто нарядов, % в срок, качество, отказы, баллы.",
        "input_schema": _schema(DaysIn),
    },
    {
        "name": "equipment_downtime",
        "description": "Простои оборудования за последние N дней: часы простоя, число нарядов, стоит ли сейчас.",
        "input_schema": _schema(DaysIn),
    },
    {
        "name": "reference_lookup",
        "description": "Поиск в справочниках: шифры неисправностей, материалы и запчасти, участки, оборудование.",
        "input_schema": _schema(LookupIn),
    },
]
for _t in TOOLS:
    _t["eager_input_streaming"] = True

TOOL_LABELS = {
    "shift_summary": "Смотрю счётчики смены",
    "find_orders": "Ищу наряды",
    "order_details": "Открываю наряд",
    "executors_status": "Проверяю исполнителей",
    "executor_ratings": "Считаю рейтинг",
    "equipment_downtime": "Смотрю простои",
    "reference_lookup": "Ищу в справочниках",
}
STAFF_ONLY = {"executors_status", "executor_ratings", "equipment_downtime"}


def _order_brief(o: WorkOrder, now: datetime) -> dict:
    return {
        "number": o.number,
        "type": "аварийный" if o.type == OrderType.EMERGENCY else "плановый",
        "status": STATUS_RU[o.status.value],
        "priority": o.priority.value,
        "description": o.description[:200],
        "workshop": o.workshop.name,
        "equipment": o.equipment.name if o.equipment else None,
        "executor": o.executor.fio if o.executor else "бригада, не взят",
        "deadline_utc": o.deadline.strftime("%d.%m %H:%M"),
        "overdue": o.overdue_at(now),
        "equipment_stopped": o.equipment_stopped,
    }


class Toolbox:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def run(self, name: str, raw: Any) -> tuple[str, bool]:
        """Возвращает (результат в JSON, is_error)."""
        handler = getattr(self, f"t_{name}", None)
        if handler is None:
            return f"Неизвестный инструмент {name}", True
        if name in STAFF_ONLY and self.user.role not in STAFF:
            return "Недоступно для роли исполнителя", True
        model = {
            "find_orders": FindOrdersIn,
            "order_details": OrderDetailsIn,
            "executor_ratings": DaysIn,
            "equipment_downtime": DaysIn,
            "reference_lookup": LookupIn,
        }.get(name, EmptyIn)
        try:
            args = model.model_validate(raw if isinstance(raw, dict) else {})
        except ValidationError as e:
            return f"Неверные параметры: {e.errors()[:2]}", True
        try:
            result = await handler(args)
        except Exception:
            log.exception("assistant tool %s failed", name)
            return "Ошибка при чтении данных", True
        return json.dumps(result, ensure_ascii=False, default=str), False

    async def t_shift_summary(self, _: EmptyIn) -> dict:
        from app.api.v1.dashboard import counters

        if self.user.role not in STAFF:
            now = utcnow()
            mine = (await self.db.scalars(visible_to(select(WorkOrder), self.user))).unique().all()
            return {
                "мои_открытые": sum(o.status in OPEN_STATUSES for o in mine),
                "мои_просроченные": sum(o.overdue_at(now) for o in mine),
                "мои_в_работе": sum(o.status == OrderStatus.IN_PROGRESS for o in mine),
            }
        return (await counters(self.db, self.user)).model_dump()

    async def t_find_orders(self, a: FindOrdersIn) -> dict:
        now = utcnow()
        stmt = visible_to(select(WorkOrder), self.user)
        if a.status:
            stmt = stmt.where(WorkOrder.status.in_([OrderStatus(s) for s in a.status]))
        elif not a.overdue:
            stmt = stmt.where(WorkOrder.status.in_(OPEN_STATUSES | {OrderStatus.COMPLETED}))
        if a.overdue:
            stmt = stmt.where(overdue_clause(now))
        if a.emergency_only:
            stmt = stmt.where(WorkOrder.type == OrderType.EMERGENCY)
        if a.text:
            stmt = stmt.where(WorkOrder.description.ilike(f"%{a.text}%"))
        if a.executor_name:
            ids = select(User.id).where(User.fio.ilike(f"%{a.executor_name}%"))
            stmt = stmt.where(WorkOrder.executor_id.in_(ids))
        stmt = stmt.order_by((WorkOrder.type == OrderType.EMERGENCY).desc(), WorkOrder.deadline).limit(a.limit)
        orders = (await self.db.scalars(stmt)).unique().all()
        return {"found": len(orders), "orders": [_order_brief(o, now) for o in orders]}

    async def t_order_details(self, a: OrderDetailsIn) -> dict:
        from app.services.workflow import can_view

        digits = "".join(ch for ch in a.number if ch.isdigit())
        order_id = int(digits[-6:]) if digits else 0
        order = await load_order(self.db, order_id)
        if order is None or not can_view(order, self.user):
            return {"error": f"Наряд {a.number} не найден или недоступен"}
        now = utcnow()
        ai = order.ai_reports[-1] if order.ai_reports else None
        return {
            **_order_brief(order, now),
            "master": order.master.fio,
            "created_utc": order.created_at.strftime("%d.%m %H:%M"),
            "work_report": order.work_report,
            "fault_code": f"{order.fault_code.code} {order.fault_code.name}" if order.fault_code else None,
            "materials": [f"{m.material_name} {m.quantity:g} {m.unit}" for m in order.materials],
            "master_score": order.master_score,
            "ai_check": {"verdict": ai.verdict.value, "score": ai.score, "explanation": ai.explanation} if ai else None,
            "history": [
                f"{e.timestamp:%d.%m %H:%M} {e.action.value}"
                + (f" → {STATUS_RU[e.to_status.value]}" if e.to_status else "")
                + (f" ({e.reason})" if e.reason else "")
                + (f" — {e.user.fio}" if e.user else " — ИИ")
                for e in order.events[-15:]
            ],
        }

    async def t_executors_status(self, _: EmptyIn) -> dict:
        rows = await executors_availability(self.db)
        return {
            "executors": [
                {
                    "fio": r.fio,
                    "specialty": r.specialty,
                    "status": r.availability.value,
                    "in_progress": r.active_orders,
                    "waiting": r.queued_orders,
                }
                for r in rows
            ]
        }

    async def t_executor_ratings(self, a: DaysIn) -> dict:
        from app.services.ai.rating import compute_ratings

        now = utcnow()
        rows = await compute_ratings(self.db, now - timedelta(days=a.days), now + timedelta(seconds=1))
        return {"days": a.days, "rating": [r.model_dump(exclude={"executor_id"}) for r in rows]}

    async def t_equipment_downtime(self, a: DaysIn) -> dict:
        from app.api.v1.dashboard import downtime

        rows = await downtime(self.db, self.user, days=a.days)
        return {"days": a.days, "equipment": [r.model_dump(exclude={"equipment_id"}) for r in rows[:20]]}

    async def t_reference_lookup(self, a: LookupIn) -> dict:
        q = f"%{a.query}%" if a.query else None
        if a.kind == "fault_codes":
            stmt = select(FaultCode).order_by(FaultCode.code)
            if q:
                stmt = stmt.where(or_(FaultCode.name.ilike(q), FaultCode.code.ilike(q)))
            items = [f"{f.code} — {f.name} ({f.category.value})" for f in await self.db.scalars(stmt.limit(40))]
        elif a.kind == "materials":
            stmt = select(Material).order_by(Material.name)
            if q:
                stmt = stmt.where(Material.name.ilike(q))
            items = [f"{m.name}, {m.unit} ({m.category.value})" for m in await self.db.scalars(stmt.limit(40))]
        elif a.kind == "workshops":
            items = [w.name for w in await self.db.scalars(select(Workshop).order_by(Workshop.name))]
        else:
            stmt = select(Equipment).order_by(Equipment.name)
            if q:
                stmt = stmt.where(or_(Equipment.name.ilike(q), Equipment.inventory_number.ilike(q)))
            items = [f"{e.name} ({e.inventory_number}, кат. {e.criticality.value})" for e in await self.db.scalars(stmt.limit(40))]
        return {"kind": a.kind, "items": items}


# ---------- диалог ----------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


ChatEvent = dict[str, Any]
ClientFactory = Callable[[str], Any]


def _default_client(api_key: str):
    import anthropic

    return anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0)


async def chat(
    db: AsyncSession,
    user: User,
    history: list[ChatMessage],
    api_key: str,
    client_factory: ClientFactory | None = None,
) -> AsyncIterator[ChatEvent]:
    """Стримит события: text (кусок ответа), tool (идёт поиск данных), error, done."""
    import anthropic

    tools = Toolbox(db, user)
    # Прошлые реплики — только текст: блоки размышлений и вызовов инструментов
    # прошлых запросов не пересылаем (они живут в рамках одного запроса).
    messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in history[-20:]]
    system = system_prompt(user, utcnow())
    json_retries = 0

    async with (client_factory or _default_client)(api_key) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                async with client.beta.messages.stream(
                    model=settings.llm_model,
                    max_tokens=8000,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                    output_config={"effort": "low"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            yield {"type": "text", "text": event.text}
                    response = await stream.get_final_message()
                json_retries = 0
            except ValueError:
                # Вход инструмента пришёл неразбираемым JSON — повторяем ход (ограниченно)
                json_retries += 1
                if json_retries > 2:
                    yield {"type": "error", "message": "Не удалось разобрать ответ модели, попробуйте ещё раз"}
                    return
                continue
            except anthropic.AuthenticationError:
                yield {"type": "error", "message": "Ключ ИИ недействителен — администратору нужно обновить его в «Настройках»"}
                return
            except anthropic.RateLimitError:
                yield {"type": "error", "message": "ИИ-сервис перегружен, повторите через минуту"}
                return
            except anthropic.APIConnectionError:
                yield {"type": "error", "message": "Нет связи с ИИ-сервисом"}
                return
            except anthropic.APIStatusError as e:
                log.warning("assistant API error %s: %s", e.status_code, e.message)
                yield {"type": "error", "message": f"Ошибка ИИ-сервиса ({e.status_code})"}
                return

            if response.stop_reason == "refusal":
                yield {"type": "error", "message": "Помощник не может ответить на этот запрос"}
                return
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                yield {"type": "done"}
                return
            if response.stop_reason == "max_tokens":
                yield {"type": "error", "message": "Ответ получился слишком длинным, уточните вопрос"}
                return

            results = []
            for block in tool_uses:
                yield {"type": "tool", "name": block.name, "label": TOOL_LABELS.get(block.name, "Смотрю данные")}
                content, is_error = await tools.run(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
            # Ответ модели добавляем без изменений (в т.ч. блоки размышлений) — история только дописывается
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})

    yield {"type": "error", "message": "Слишком много шагов поиска — сформулируйте вопрос конкретнее"}
