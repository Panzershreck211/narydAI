from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import DB, AdminUser, CurrentUser, MasterUser, StaffUser
from app.core.security import hash_secret
from app.models import Brigade, User
from app.models.enums import Role
from app.schemas.user import (
    ExecutorAvailability,
    PasswordReset,
    ShiftUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.availability import executors_availability

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user(db: DB, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    return user


async def _check_brigade(db: DB, brigade_id: int | None) -> None:
    if brigade_id is not None and await db.get(Brigade, brigade_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Бригада не найдена")


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Регистрация сотрудника")
async def create_user(body: UserCreate, db: DB, _: AdminUser):
    await _check_brigade(db, body.brigade_id)
    user = User(
        **body.model_dump(exclude={"password", "pin"}),
        password_hash=hash_secret(body.password),
        pin_hash=hash_secret(body.pin) if body.pin else None,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Логин уже занят") from None
    return UserOut.from_user(user)


@router.get("", response_model=list[UserOut])
async def list_users(
    db: DB,
    _: StaffUser,
    role: Role | None = None,
    brigade_id: int | None = None,
    active: bool | None = None,
    q: str | None = Query(default=None, description="Поиск по ФИО или логину"),
):
    stmt = select(User).order_by(User.fio)
    if role:
        stmt = stmt.where(User.role == role)
    if brigade_id:
        stmt = stmt.where(User.brigade_id == brigade_id)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(User.fio.ilike(like) | User.login.ilike(like))
    return [UserOut.from_user(u) for u in await db.scalars(stmt)]


@router.get(
    "/executors/availability",
    response_model=list[ExecutorAvailability],
    summary="Исполнители со статусом свободен/занят/очередь/не на смене",
)
async def availability(db: DB, _: StaffUser, brigade_id: int | None = None):
    return await executors_availability(db, brigade_id)


@router.patch("/me/shift", response_model=UserOut, summary="Исполнитель отмечает выход на смену")
async def set_my_shift(body: ShiftUpdate, db: DB, user: CurrentUser):
    user.on_shift = body.on_shift
    await db.commit()
    return UserOut.from_user(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: DB, _: StaffUser):
    return UserOut.from_user(await _get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut, summary="Изменение данных и роли")
async def update_user(user_id: int, body: UserUpdate, db: DB, admin: AdminUser):
    user = await _get_user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("role", Role.ADMIN) != Role.ADMIN or data.get("is_active") is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя снять с себя роль администратора или заблокировать себя")
    if "brigade_id" in data:
        await _check_brigade(db, data["brigade_id"])
    for key, value in data.items():
        setattr(user, key, value)
    await db.commit()
    return UserOut.from_user(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: int, body: PasswordReset, db: DB, _: AdminUser):
    user = await _get_user(db, user_id)
    user.password_hash = hash_secret(body.password)
    if body.pin:
        user.pin_hash = hash_secret(body.pin)
    user.failed_pin_attempts = 0
    user.locked_until = None
    await db.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Блокировка (мягкое удаление)")
async def deactivate_user(user_id: int, db: DB, admin: AdminUser):
    user = await _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя заблокировать себя")
    user.is_active = False
    await db.commit()


@router.patch("/{user_id}/shift", response_model=UserOut, summary="Отметить выход на смену / уход со смены")
async def set_shift(user_id: int, body: ShiftUpdate, db: DB, _: MasterUser):
    user = await _get_user(db, user_id)
    user.on_shift = body.on_shift
    await db.commit()
    return UserOut.from_user(user)
