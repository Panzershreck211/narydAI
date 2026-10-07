"""ИИ-проверка закрытого наряда.

Слой 1 — детерминированные правила (всегда): полнота, соответствие отчёта проблеме,
логичность материалов, правдоподобность сроков, фотофиксация.
Слой 2 — опционально Gemini (см. llm_judge.py): смысловая оценка отчёта.
"""

from dataclasses import asdict, dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIReport, Material, WorkOrder
from app.models.enums import FAULT_CATEGORY_RU, AIVerdict, FaultCategory, OrderAction, OrderType, PhotoType
from app.services.ai import text
from app.services.ai.llm_judge import LLMVerdict
from app.services.ai.photo_checker import assess_photos
from app.services.workflow import log_event

PENALTY = {"error": 1.5, "warn": 0.75, "info": 0.0}

# Какие категории материалов логичны для категории неисправности
COMPATIBLE: dict[FaultCategory, set[FaultCategory]] = {
    FaultCategory.MECHANICAL: {FaultCategory.MECHANICAL, FaultCategory.LUBRICATION},
    FaultCategory.HYDRAULIC: {FaultCategory.HYDRAULIC, FaultCategory.LUBRICATION, FaultCategory.MECHANICAL},
    FaultCategory.ELECTRICAL: {FaultCategory.ELECTRICAL, FaultCategory.INSTRUMENTATION},
    FaultCategory.INSTRUMENTATION: {FaultCategory.INSTRUMENTATION, FaultCategory.ELECTRICAL},
    FaultCategory.PNEUMATIC: {FaultCategory.PNEUMATIC, FaultCategory.MECHANICAL},
    FaultCategory.LUBRICATION: {FaultCategory.LUBRICATION, FaultCategory.MECHANICAL},
}


@dataclass
class Check:
    name: str
    severity: str  # ok | info | warn | error
    message: str


@dataclass
class CheckResult:
    verdict: AIVerdict
    score: float
    photo_score: float | None
    checks: list[Check] = field(default_factory=list)
    source: str = "rules"

    @property
    def explanation(self) -> str:
        problems = [c.message for c in self.checks if c.severity in ("warn", "error")]
        if not problems:
            return "Наряд заполнен полно, отчёт соответствует проблеме, замечаний нет."
        return "Замечания: " + "; ".join(problems)


def check_order(order: WorkOrder, catalog: dict[int, Material]) -> CheckResult:
    checks: list[Check] = []
    add = lambda name, sev, msg: checks.append(Check(name, sev, msg))  # noqa: E731

    report = (order.work_report or "").strip()
    fault = order.fault_code

    # 1. Полнота
    if len(report) < 30 or len(report.split()) < 5:
        add("completeness", "error", "Описание выполненных работ слишком короткое (нужно ≥ 5 слов)")
    else:
        add("completeness", "ok", "Описание работ заполнено")
    if fault is None:
        add("fault_code", "error", "Не указан шифр неисправности")
    if text.mentions_replacement(report) and not order.materials:
        add("materials_missing", "warn", "В отчёте упомянута замена/установка, но материалы не списаны")

    # 2. Соответствие отчёта проблеме
    context = f"{order.description} {order.equipment.name if order.equipment else ''}"
    sim = text.overlap(context, report)
    report_cats = text.category_hits(report)
    problem_cats = text.category_hits(context)
    if sim >= 0.15 or (set(report_cats) & set(problem_cats)):
        add("relevance", "ok", f"Отчёт соотносится с описанием проблемы (совпадение {sim:.0%})")
    else:
        add("relevance", "warn", "Отчёт слабо связан с описанием проблемы — проверьте, та ли работа выполнена")

    if fault is not None and report_cats:
        dominant = max(report_cats, key=report_cats.get)
        if fault.category not in report_cats and fault.category != FaultCategory.OTHER:
            add(
                "fault_vs_report",
                "warn",
                f"Шифр «{fault.code}» ({FAULT_CATEGORY_RU[fault.category]}) не согласуется с текстом отчёта "
                f"(по тексту — {FAULT_CATEGORY_RU[dominant]})",
            )

    # 3. Логичность материалов
    for m in order.materials:
        ref = catalog.get(m.material_id) if m.material_id else None
        if ref is None:
            add("material_unknown", "info", f"«{m.material_name}» отсутствует в справочнике")
            continue
        if ref.max_per_order and m.quantity > ref.max_per_order:
            add(
                "material_qty",
                "warn",
                f"Списано {m.quantity:g} {m.unit} «{ref.name}» — больше типового максимума {ref.max_per_order:g}",
            )
        if (
            fault is not None
            and ref.category != FaultCategory.OTHER
            and fault.category in COMPATIBLE
            and ref.category not in COMPATIBLE[fault.category]
        ):
            add(
                "material_category",
                "warn",
                f"Материал «{ref.name}» ({FAULT_CATEGORY_RU[ref.category]}) нетипичен для неисправности: {FAULT_CATEGORY_RU[fault.category]}",
            )

    # 4. Правдоподобность сроков
    if order.started_at and order.completed_at:
        spent = order.completed_at - order.started_at
        if spent < timedelta(minutes=5):
            add("duration", "warn", f"Работа выполнена подозрительно быстро ({int(spent.total_seconds() // 60)} мин)")
    if order.completed_at and order.completed_at > order.deadline:
        late_min = int((order.completed_at - order.deadline).total_seconds() // 60)
        add("deadline", "info", f"Наряд закрыт с опозданием на {late_min} мин")

    # 5. Фотофиксация
    before = [p.meta or {} for p in order.photos if p.type == PhotoType.BEFORE]
    after = [p.meta or {} for p in order.photos if p.type == PhotoType.AFTER]
    photo_score: float | None = None
    if after or order.type == OrderType.EMERGENCY:
        pc = assess_photos(before, after, order.created_at)
        photo_score = pc.score
        for issue in pc.issues:
            add("photo", "warn", issue)
        for note in pc.notes:
            add("photo", "info", note)

    rules_score = max(1.0, 5.0 - sum(PENALTY.get(c.severity, 0) for c in checks))
    score = rules_score if photo_score is None else 0.7 * rules_score + 0.3 * photo_score
    return CheckResult(_verdict(score, checks), round(score, 2), photo_score, checks)


def merge_llm(result: CheckResult, llm: LLMVerdict) -> CheckResult:
    """Добавляет к правилам смысловую оценку LLM."""
    checks = list(result.checks)
    checks.append(Check("llm_relevance", "ok" if llm.relevance >= 4 else "warn", f"LLM: {llm.summary}"))
    if not llm.materials_logical:
        checks.append(Check("llm_materials", "warn", "LLM: списанные материалы не согласуются с работой"))
    checks.extend(Check("llm_issue", "warn", f"LLM: {i}") for i in llm.issues[:5])
    score = round(0.6 * result.score + 0.4 * llm.relevance, 2)
    return CheckResult(_verdict(score, checks), score, result.photo_score, checks, source="rules+llm")


def _verdict(score: float, checks: list[Check]) -> AIVerdict:
    errors = sum(1 for c in checks if c.severity == "error")
    if score < 2.5 or errors >= 2:
        return AIVerdict.REJECTED
    if score >= 4.0 and errors == 0:
        return AIVerdict.OK
    return AIVerdict.NEEDS_REVIEW


async def load_catalog(db: AsyncSession, order: WorkOrder) -> dict[int, Material]:
    ids = {m.material_id for m in order.materials if m.material_id}
    if not ids:
        return {}
    return {m.id: m for m in await db.scalars(select(Material).where(Material.id.in_(ids)))}


async def save_report(db: AsyncSession, order: WorkOrder, result: CheckResult) -> AIReport:
    report = AIReport(
        order_id=order.id,
        verdict=result.verdict,
        score=result.score,
        photo_score=result.photo_score,
        explanation=result.explanation,
        checks=[asdict(c) for c in result.checks],
        source=result.source,
    )
    db.add(report)
    verdict_ru = {"ok": "замечаний нет", "needs_review": "нужна проверка", "rejected": "есть нарушения"}[result.verdict.value]
    log_event(db, order, None, OrderAction.AI_CHECK, reason=f"{verdict_ru}, {result.score:.1f}/5")
    return report
