import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

log = logging.getLogger(__name__)

TokenType = Literal["access", "refresh"]


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(secret: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(secret.encode(), hashed.encode())
    except ValueError:
        return False


JWT_SECRET_SETTING = "jwt_secret"
# Значения-заглушки из прошлых версий и .env.example — подписывать ими токены нельзя
_PLACEHOLDERS = {"change-me-in-production-please-32+chars", "replace-with-64-random-chars"}


def is_weak_secret(secret: str) -> bool:
    return len(secret) < 32 or secret in _PLACEHOLDERS


async def ensure_jwt_secret(db: AsyncSession) -> None:
    """Если JWT_SECRET не задан, берёт ключ этой установки из БД (или создаёт его).

    Так «из коробки» у каждой установки свой секрет, и он переживает перезапуски.
    """
    from app.models import AppSetting

    if not is_weak_secret(settings.jwt_secret):
        return
    row = await db.get(AppSetting, JWT_SECRET_SETTING)
    if row is None:
        db.add(AppSetting(key=JWT_SECRET_SETTING, value=secrets.token_hex(32)))
        try:
            await db.commit()
            log.warning("JWT_SECRET не задан — сгенерирован ключ установки и сохранён в БД")
        except IntegrityError:  # параллельно стартовал другой процесс API
            await db.rollback()
        row = await db.get(AppSetting, JWT_SECRET_SETTING)
    settings.jwt_secret = row.value


def _secret() -> str:
    if is_weak_secret(settings.jwt_secret):
        raise RuntimeError("JWT-секрет не настроен: задайте JWT_SECRET (не короче 32 символов)")
    return settings.jwt_secret


# bcrypt намеренно медленный (~0.2 с) — в обработчиках запускаем его в потоке,
# чтобы серия входов не останавливала event loop (WebSocket, остальные запросы).
async def hash_secret_async(secret: str) -> str:
    return await asyncio.to_thread(hash_secret, secret)


async def verify_secret_async(secret: str, hashed: str | None) -> bool:
    return await asyncio.to_thread(verify_secret, secret, hashed)


def create_token(user_id: int, role: str, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    payload = {"sub": str(user_id), "role": role, "type": token_type, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, _secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Raises jwt.PyJWTError on any problem with the token."""
    payload = jwt.decode(token, _secret(), algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload
