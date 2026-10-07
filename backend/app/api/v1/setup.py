"""Первоначальная настройка: создание первого администратора прямо из панели.

Работает, только пока в системе нет ни одного активного администратора.
Как только он создан, эндпоинт отвечает 409 — повторно «захватить» систему нельзя.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import _tokens
from app.core.deps import DB
from app.core.security import hash_secret_async
from app.models import User
from app.models.enums import Role
from app.schemas.auth import TokenPair
from app.seed import seed_references

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupIn(BaseModel):
    fio: str = Field(min_length=3, max_length=200)
    login: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=128)
    load_examples: bool = False


async def _has_admin(db: AsyncSession) -> bool:
    count = await db.scalar(
        select(func.count(User.id)).where(User.role == Role.ADMIN, User.is_active.is_(True))
    )
    return bool(count)


@router.get("/status", response_model=SetupStatus, summary="Нужна ли первоначальная настройка")
async def setup_status(db: DB):
    return SetupStatus(needs_setup=not await _has_admin(db))


@router.post("", response_model=TokenPair, status_code=status.HTTP_201_CREATED, summary="Создать первого администратора")
async def run_setup(body: SetupIn, db: DB):
    if db.bind.dialect.name == "postgresql":
        # Два одновременных запроса не создадут двух «первых» администраторов: второй
        # дождётся commit первого и получит 409. (SQLite и так пишет последовательно.)
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('naryad-setup'))"))
    if await _has_admin(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Система уже настроена — войдите под администратором")
    if await db.scalar(select(User.id).where(User.login == body.login)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Логин уже занят")

    admin = User(login=body.login, fio=body.fio.strip(), role=Role.ADMIN, password_hash=await hash_secret_async(body.password))
    db.add(admin)
    if body.load_examples:
        await seed_references(db)
    await db.commit()
    return _tokens(admin)
