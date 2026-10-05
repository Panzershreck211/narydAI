"""Опциональная смысловая проверка наряда через Claude.

Включается, если ключ Claude задан в настройках панели или в ANTHROPIC_API_KEY. Любая ошибка (нет ключа, сеть, отказ
модели) не ломает закрытие наряда — остаётся оценка по правилам.
"""

import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.core.config import settings

log = logging.getLogger(__name__)

SYSTEM = (
    "Ты — инженер-контролёр ремонтной службы горно-обогатительного предприятия. "
    "Проверяешь закрытый рабочий наряд: соответствует ли описание выполненных работ "
    "заявленной проблеме и шифру неисправности, логичны ли списанные материалы "
    "(тип и количество). Отвечай кратко, по-русски, без домыслов: если данных мало — так и скажи."
)


class LLMVerdict(BaseModel):
    relevance: int = Field(ge=1, le=5, description="1 — отчёт не о той проблеме, 5 — полностью соответствует")
    materials_logical: bool
    issues: list[str]
    summary: str


@dataclass
class OrderFacts:
    problem: str
    equipment: str | None
    fault: str | None
    report: str
    materials: list[str]


def _schema() -> dict:
    schema = LLMVerdict.model_json_schema()
    schema["additionalProperties"] = False
    for prop in schema["properties"].values():  # structured outputs не поддерживает min/max
        prop.pop("minimum", None)
        prop.pop("maximum", None)
    return schema


async def judge(facts: OrderFacts, api_key: str | None) -> LLMVerdict | None:
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK недоступен — LLM-проверка пропущена")
        return None

    prompt = (
        f"Проблема (из наряда): {facts.problem}\n"
        f"Оборудование: {facts.equipment or 'не указано'}\n"
        f"Шифр неисправности: {facts.fault or 'не указан'}\n"
        f"Отчёт исполнителя: {facts.report}\n"
        f"Списанные материалы: {', '.join(facts.materials) or 'нет'}"
    )
    try:
        async with anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0) as client:
            response = await client.beta.messages.create(
                model=settings.llm_model,
                max_tokens=2000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": _schema()},
                },
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
    except anthropic.APIConnectionError:
        log.warning("LLM недоступна (сеть)")
        return None
    except anthropic.RateLimitError:
        log.warning("LLM: превышен лимит запросов")
        return None
    except anthropic.APIStatusError as e:
        log.warning("LLM вернула ошибку %s: %s", e.status_code, e.message)
        return None

    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("LLM не дала ответ: %s", response.stop_reason)
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    try:
        verdict = LLMVerdict.model_validate(json.loads(text))
    except ValueError:
        log.warning("LLM вернула невалидный JSON")
        return None
    verdict.relevance = min(5, max(1, verdict.relevance))
    return verdict
