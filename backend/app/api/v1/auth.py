from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.security import create_token, decode_token, hash_secret, verify_secret
from app.db.base import utcnow
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    PinLoginRequest,
    RefreshRequest,
    SetPinRequest,
    TokenPair,
)
from app.schemas.user import DeviceTokenIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

_bad_credentials = HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")


def _tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, user.role.value, "access"),
        refresh_token=create_token(user.id, user.role.value, "refresh"),
        user=UserOut.from_user(user),
    )


async def _by_login(db: DB, login: str) -> User | None:
    return await db.scalar(select(User).where(User.login == login.strip()))


async def _password_login(db: DB, login: str, password: str) -> TokenPair:
    user = await _by_login(db, login)
    if user is None or not user.is_active or not verify_secret(password, user.password_hash):
        raise _bad_credentials
    return _tokens(user)


@router.post("/login", response_model=TokenPair, summary="Вход по логину и паролю")
async def login(body: LoginRequest, db: DB):
    return await _password_login(db, body.login, body.password)


@router.post("/token", response_model=TokenPair, include_in_schema=False)
async def token_form(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    """OAuth2-совместимый вход — для кнопки Authorize в Swagger UI."""
    return await _password_login(db, form.username, form.password)


@router.post("/pin-login", response_model=TokenPair, summary="Быстрый вход по ПИН-коду (для рабочих)")
async def pin_login(body: PinLoginRequest, db: DB):
    user = await _by_login(db, body.login)
    if user is None or not user.is_active or user.pin_hash is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный табельный номер или ПИН")

    now = utcnow()
    if user.locked_until and user.locked_until > now:
        wait = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Вход по ПИН заблокирован, повторите через {wait} мин")

    if not verify_secret(body.pin, user.pin_hash):
        user.failed_pin_attempts += 1
        if user.failed_pin_attempts >= settings.pin_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.pin_lock_minutes)
            user.failed_pin_attempts = 0
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный табельный номер или ПИН")

    user.failed_pin_attempts = 0
    user.locked_until = None
    await db.commit()
    return _tokens(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DB):
    try:
        payload = decode_token(body.refresh_token, "refresh")
        user = await db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный refresh-токен") from None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь заблокирован")
    return _tokens(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return UserOut.from_user(user)


@router.post("/me/pin", status_code=status.HTTP_204_NO_CONTENT, summary="Установить/сменить свой ПИН")
async def set_pin(body: SetPinRequest, user: CurrentUser, db: DB):
    if not verify_secret(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Неверный пароль")
    user.pin_hash = hash_secret(body.pin)
    await db.commit()


@router.post("/me/device", status_code=status.HTTP_204_NO_CONTENT, summary="Регистрация FCM-токена устройства")
async def register_device(body: DeviceTokenIn, user: CurrentUser, db: DB):
    user.fcm_token = body.fcm_token
    await db.commit()
