import json
import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import DB, AdminUser, CurrentUser
from app.core.i18n import get_lang, tr
from app.db.session import SessionLocal
from app.models import AppSetting, User
from app.services.ai import assistant, gemini
from app.services.ai.llm_client import API_KEY_SETTING, get_api_key, key_hint

log = logging.getLogger(__name__)
router = APIRouter(tags=["assistant"])


# ---------- настройки (администратор) ----------


class AssistantSettingsOut(BaseModel):
    configured: bool
    source: str | None  # panel | env
    key_hint: str | None
    model: str


class ApiKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=300, description="Ключ Google AI Studio (AIza…)")


@router.get("/settings/assistant", response_model=AssistantSettingsOut, summary="Состояние подключения ИИ")
async def get_assistant_settings(db: DB, _: AdminUser):
    key, source = await get_api_key(db)
    return AssistantSettingsOut(configured=bool(key), source=source, key_hint=key_hint(key) if key else None, model=settings.llm_model)


@router.put("/settings/assistant", response_model=AssistantSettingsOut, summary="Сохранить ключ Gemini (с проверкой)")
async def set_assistant_key(body: ApiKeyIn, db: DB, _: AdminUser):
    key = body.api_key.strip()
    try:
        await gemini.check_key(key)
    except gemini.GeminiError as e:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY if e.status in (400, 401, 403, 404) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code, e.message) from None

    row = await db.get(AppSetting, API_KEY_SETTING)
    if row:
        row.value = key
    else:
        db.add(AppSetting(key=API_KEY_SETTING, value=key))
    await db.commit()
    return AssistantSettingsOut(configured=True, source="panel", key_hint=key_hint(key), model=settings.llm_model)


@router.delete("/settings/assistant", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить ключ из панели")
async def delete_assistant_key(db: DB, _: AdminUser):
    row = await db.get(AppSetting, API_KEY_SETTING)
    if row:
        await db.delete(row)
        await db.commit()


# ---------- чат ----------


class AssistantStatus(BaseModel):
    configured: bool


class ChatIn(BaseModel):
    # модели уходят только последние реплики (assistant.context_window) — длинную историю не отклоняем
    messages: list[assistant.ChatMessage] = Field(min_length=1, max_length=200)


@router.get("/assistant/status", response_model=AssistantStatus)
async def assistant_status(db: DB, _: CurrentUser):
    key, _src = await get_api_key(db)
    return AssistantStatus(configured=bool(key))


@router.post("/assistant/chat", summary="Чат с ИИ-помощником (Server-Sent Events)")
async def assistant_chat(body: ChatIn, db: DB, user: CurrentUser):
    if body.messages[-1].role != "user":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Последнее сообщение должно быть от пользователя")
    key, _src = await get_api_key(db)
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ИИ-помощник не подключён: администратору нужно добавить ключ в «Настройках»")
    user_id = user.id
    lang = get_lang()

    def sse(event: dict) -> str:
        # служебные сообщения (ошибки, «Ищу наряды…») — на языке интерфейса; ответ модели уже на нём
        for field in ("message", "label"):
            if field in event:
                event = {**event, field: tr(event[field], lang)}
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def events():
        # Своя сессия: зависимость get_db закрывается раньше, чем дочитается поток
        async with SessionLocal() as session:
            me = await session.get(User, user_id)
            try:
                async for event in assistant.chat(session, me, body.messages, key, lang=lang):
                    yield sse(event)
            except Exception:
                log.exception("assistant chat failed")
                yield sse({"type": "error", "message": "Внутренняя ошибка помощника"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # nginx не буферизует поток
    )
