"""Клиент Google Gemini API (generateContent) на httpx — без SDK и нативных зависимостей.

Ключ бесплатно выдаёт Google AI Studio (aistudio.google.com → Get API key). Бесплатный тариф
ограничен по числу запросов в минуту/сутки; при превышении API отвечает 429.
"""

import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

ClientFactory = Callable[[], httpx.AsyncClient]


class GeminiError(Exception):
    """Ошибка Gemini с понятным пользователю текстом (по-русски, переводится на выдаче)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


# Ошибки, при которых пробуем следующую модель: перегрузка, лимит, модель недоступна для ключа
RETRYABLE = {404, 429, 500, 502, 503, 504}


def models() -> list[str]:
    """Основная модель и запасные (LLM_FALLBACK_MODELS) — без повторов."""
    out: list[str] = []
    for m in [settings.llm_model, *settings.llm_fallback_models]:
        if m and m not in out:
            out.append(m)
    return out


def default_client() -> httpx.AsyncClient:
    # Ждём ответа не дольше 30 с: перегруженная модель иногда «молчит» — тогда переходим к запасной
    return httpx.AsyncClient(base_url=settings.gemini_base_url, timeout=httpx.Timeout(30.0, connect=10.0))


_TIMEOUT = "ИИ-сервис не ответил вовремя — повторите через минуту"


def _error_for(status: int, body: str) -> GeminiError:
    try:
        detail = json.loads(body).get("error", {})
    except ValueError:
        detail = {}
    reason = str(detail.get("status", ""))
    log.warning("Gemini %s %s: %s", status, reason, str(detail.get("message", body))[:300])
    if status in (401, 403) or (status == 400 and "API_KEY" in body):
        return GeminiError("Ключ Gemini недействителен — администратору нужно обновить его в «Настройках»", status)
    if status == 429:
        return GeminiError("Исчерпан лимит бесплатного тарифа Gemini — повторите через минуту", status)
    if status == 404:
        return GeminiError("Модель Gemini недоступна для этого ключа — проверьте LLM_MODEL", status)
    if status >= 500:
        return GeminiError("ИИ-сервис перегружен, повторите через минуту", status)
    return GeminiError(f"Ошибка ИИ-сервиса ({status})", status)


def _headers(api_key: str) -> dict[str, str]:
    # ключ — в заголовке, а не в URL: не попадает в логи прокси
    return {"x-goog-api-key": api_key, "Content-Type": "application/json"}


async def generate(api_key: str, body: dict[str, Any], client_factory: ClientFactory | None = None) -> dict[str, Any]:
    last = GeminiError(_TIMEOUT)
    for model in models():
        try:
            async with (client_factory or default_client)() as client:
                r = await client.post(f"/models/{model}:generateContent", json=body, headers=_headers(api_key))
        except httpx.TimeoutException:
            log.warning("Gemini %s не ответила вовремя — пробую запасную модель", model)
            last = GeminiError(_TIMEOUT)
            continue
        except httpx.HTTPError:
            raise GeminiError("Нет связи с ИИ-сервисом") from None
        if r.status_code == 200:
            return r.json()
        last = _error_for(r.status_code, r.text)
        if r.status_code not in RETRYABLE:
            raise last
    raise last


async def stream_generate(
    api_key: str, body: dict[str, Any], client_factory: ClientFactory | None = None
) -> AsyncIterator[dict[str, Any]]:
    """Ответ по частям (SSE): каждый элемент — GenerateContentResponse.

    Если модель перегружена или молчит до первого фрагмента — запрос уходит запасной модели.
    """
    last = GeminiError(_TIMEOUT)
    for model in models():
        started = False
        try:
            async with (client_factory or default_client)() as client:
                async with client.stream(
                    "POST",
                    f"/models/{model}:streamGenerateContent",
                    params={"alt": "sse"},
                    json=body,
                    headers=_headers(api_key),
                ) as r:
                    if r.status_code != 200:
                        last = _error_for(r.status_code, (await r.aread()).decode("utf-8", "replace"))
                        if r.status_code in RETRYABLE:
                            continue
                        raise last
                    async for line in r.aiter_lines():
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload:
                                started = True
                                yield json.loads(payload)
            return
        except httpx.TimeoutException:
            if started:
                raise GeminiError(_TIMEOUT) from None
            log.warning("Gemini %s не ответила вовремя — пробую запасную модель", model)
            last = GeminiError(_TIMEOUT)
        except httpx.HTTPError:
            raise GeminiError("Нет связи с ИИ-сервисом") from None
    raise last


async def check_key(api_key: str, client_factory: ClientFactory | None = None) -> None:
    """Проверка ключа запросом описания модели — бесплатно и не тратит лимит генерации."""
    try:
        async with (client_factory or default_client)() as client:
            r = await client.get(f"/models/{settings.llm_model}", headers=_headers(api_key))
    except httpx.HTTPError:
        raise GeminiError("Сервер не может связаться с Google Gemini — проверьте доступ в интернет") from None
    if r.status_code in (400, 401, 403):
        raise GeminiError("Ключ не принят сервисом Gemini — проверьте, что скопировали его полностью", r.status_code)
    if r.status_code != 200:
        raise _error_for(r.status_code, r.text)


def candidate(response: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Части ответа первого кандидата и причина остановки."""
    if (response.get("promptFeedback") or {}).get("blockReason"):
        return [], "BLOCKED"
    cands = response.get("candidates") or [{}]
    return (cands[0].get("content") or {}).get("parts") or [], cands[0].get("finishReason")


def response_text(response: dict[str, Any]) -> str:
    parts, _ = candidate(response)
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


_KEEP = ("type", "description", "enum", "format", "minimum", "maximum", "required", "nullable")


def to_schema(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> dict[str, Any]:
    """JSON Schema от Pydantic → подмножество OpenAPI, которое принимает Gemini ($ref, anyOf, title — нельзя)."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return to_schema(defs[schema["$ref"].rsplit("/", 1)[-1]], defs)
    if "anyOf" in schema:
        options = [s for s in schema["anyOf"] if s.get("type") != "null"]
        out = to_schema(options[0], defs)
        if len(options) < len(schema["anyOf"]):
            out["nullable"] = True
        if "description" in schema:
            out["description"] = schema["description"]
        return out
    out = {k: schema[k] for k in _KEEP if k in schema}
    if schema.get("type") == "object":
        out["properties"] = {k: to_schema(v, defs) for k, v in schema.get("properties", {}).items()}
    if schema.get("type") == "array" and "items" in schema:
        out["items"] = to_schema(schema["items"], defs)
    return out
