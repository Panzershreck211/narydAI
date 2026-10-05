import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import AIReport, User, WorkOrder
from app.models.enums import AIVerdict, Role
from app.services.ai import llm_judge
from app.services.ai.llm_client import get_api_key
from app.services.ai.order_checker import (
    check_order,
    load_catalog,
    merge_llm,
    save_report,
)
from app.services.notifications import deliver_outbox, notify
from app.services.orders import load_order

log = logging.getLogger(__name__)

VERDICT_RU = {AIVerdict.OK: "замечаний нет", AIVerdict.NEEDS_REVIEW: "нужна проверка", AIVerdict.REJECTED: "есть нарушения"}


async def run_rules_check(db: AsyncSession, order: WorkOrder) -> AIReport:
    result = check_order(order, await load_catalog(db, order))
    return await save_report(db, order, result)


async def run_llm_enrichment(order_id: int) -> None:
    """Фоновая задача после закрытия наряда: уточняет оценку через Claude и уведомляет мастера."""
    async with SessionLocal() as db:
        api_key, _ = await get_api_key(db)
        if not api_key:
            return
        order = await load_order(db, order_id)
        if order is None:
            return
        facts = llm_judge.OrderFacts(
            problem=order.description,
            equipment=order.equipment.name if order.equipment else None,
            fault=f"{order.fault_code.code} {order.fault_code.name}" if order.fault_code else None,
            report=order.work_report or "",
            materials=[f"{m.material_name} {m.quantity:g} {m.unit}" for m in order.materials],
        )
        verdict = await llm_judge.judge(facts, api_key)
        if verdict is None:
            return
        base = check_order(order, await load_catalog(db, order))
        report = await save_report(db, order, merge_llm(base, verdict))
        master = await db.get(User, order.master_id)
        await notify(
            db,
            [master],
            kind="ai",
            title=f"ИИ-проверка {order.number}: {VERDICT_RU[report.verdict]}",
            body=f"Оценка {report.score:.1f}/5. {report.explanation[:300]}",
            order=order,
            emergency=False,
        )
        await db.commit()
        await deliver_outbox(db)


async def staff_to_alert(db: AsyncSession, order: WorkOrder) -> list[User]:
    """Мастер наряда + все мастера на смене (на случай пересменки)."""
    masters = list(
        await db.scalars(select(User).where(User.role == Role.MASTER, User.on_shift.is_(True), User.is_active.is_(True)))
    )
    master = await db.get(User, order.master_id)
    return [master, *masters]
