from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.models.enums import Role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/token")

DB = Annotated[AsyncSession, Depends(get_db)]

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Недействительный токен",
    headers={"WWW-Authenticate": "Bearer"},
)


async def user_from_token(db: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token, "access")
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _credentials_error from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_error
    return user


async def get_current_user(db: DB, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    return await user_from_token(db, token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Зависимость RBAC: пропускает только перечисленные роли."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для этой операции")
        return user

    return checker


AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
MasterUser = Annotated[User, Depends(require_roles(Role.MASTER, Role.ADMIN))]
ExecutorUser = Annotated[User, Depends(require_roles(Role.EXECUTOR))]
StaffUser = Annotated[User, Depends(require_roles(Role.MASTER, Role.MANAGER, Role.ADMIN))]
AnalyticsUser = Annotated[User, Depends(require_roles(Role.MANAGER, Role.MASTER, Role.ADMIN))]
