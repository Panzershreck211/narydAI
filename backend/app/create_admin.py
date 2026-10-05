"""Создание первого администратора (или восстановление доступа).

    python -m app.create_admin --login aseitkali --fio "Сейткали Айгерим Маратовна"

Пароль спрашивается дважды и не попадает в историю команд. Для скриптов можно
передать --password или переменную окружения ADMIN_PASSWORD.

Если логин уже есть — пользователю задаётся новый пароль, роль «Администратор»
и снимается блокировка. Так восстанавливают доступ, если пароль админа забыт.
"""

import argparse
import asyncio
import getpass
import os
import re
import sys

from sqlalchemy import select

from app.core.security import hash_secret
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User
from app.models.enums import Role

LOGIN_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,50}$")


async def create_admin(login: str, fio: str | None, password: str) -> tuple[User, bool]:
    """Возвращает (пользователь, создан_ли_новый)."""
    if not LOGIN_RE.match(login):
        raise ValueError("Логин: 3–50 символов, латиница, цифры, . _ -")
    if len(password) < 8:
        raise ValueError("Пароль должен быть не короче 8 символов")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.login == login))
        created = user is None
        if created:
            if not fio or len(fio.strip()) < 3:
                raise ValueError("Для нового администратора укажите ФИО (--fio)")
            user = User(login=login, fio=fio.strip(), role=Role.ADMIN, password_hash=hash_secret(password))
            db.add(user)
        else:
            user.role = Role.ADMIN
            user.password_hash = hash_secret(password)
            user.is_active = True
            user.failed_pin_attempts = 0
            user.locked_until = None
            if fio:
                user.fio = fio.strip()
        await db.commit()
        return user, created


def _read_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    if os.environ.get("ADMIN_PASSWORD"):
        return os.environ["ADMIN_PASSWORD"]
    if not sys.stdin.isatty():
        sys.exit("Нет терминала для ввода пароля: передайте --password или ADMIN_PASSWORD")
    first = getpass.getpass("Пароль (не короче 8 символов): ")
    if first != getpass.getpass("Повторите пароль: "):
        sys.exit("Пароли не совпадают")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать администратора НарядAI или восстановить доступ")
    parser.add_argument("--login", required=True, help="логин для входа в панель (латиница)")
    parser.add_argument("--fio", help="ФИО (обязательно для нового пользователя)")
    parser.add_argument("--password", help="пароль (лучше не указывать — команда спросит сама)")
    args = parser.parse_args()

    try:
        user, created = asyncio.run(create_admin(args.login, args.fio, _read_password(args)))
    except ValueError as e:
        sys.exit(f"Ошибка: {e}")
    action = "создан" if created else "получил роль администратора и новый пароль"
    print(f"Готово: пользователь «{user.login}» ({user.fio}) {action}. Входите в панель под этим логином.")


if __name__ == "__main__":
    main()
