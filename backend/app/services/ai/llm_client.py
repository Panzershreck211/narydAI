"""Ключ Gemini: из настроек панели (приоритет) или из переменной окружения GEMINI_API_KEY."""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AppSetting

API_KEY_SETTING = "gemini_api_key"

KeySource = Literal["panel", "env"]


async def get_api_key(db: AsyncSession) -> tuple[str | None, KeySource | None]:
    row = await db.get(AppSetting, API_KEY_SETTING)
    if row and row.value:
        return row.value, "panel"
    if settings.gemini_api_key:
        return settings.gemini_api_key, "env"
    return None, None


def key_hint(key: str) -> str:
    """AIzaSyAB…wxyz — чтобы админ узнал свой ключ, не видя его целиком."""
    return f"{key[:8]}…{key[-4:]}" if len(key) > 20 else "…"
