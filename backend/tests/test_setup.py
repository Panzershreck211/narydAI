"""Первоначальная настройка из панели: первый администратор без консоли."""

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models import User, Workshop
from app.models.enums import Role

API = "/api/v1"
BODY = {"fio": "Первый Админ Тестович", "login": "first-admin", "password": "FirstAdmin#1"}


async def test_setup_closed_when_admin_exists(client):
    assert (await client.get(f"{API}/setup/status")).json() == {"needs_setup": False}
    r = await client.post(f"{API}/setup", json=BODY)
    assert r.status_code == 409
    assert (await client.post(f"{API}/auth/login", json={"login": "first-admin", "password": "FirstAdmin#1"})).status_code == 401


async def test_setup_creates_first_admin(client):
    # Имитируем пустую систему: временно отключаем всех администраторов
    async with SessionLocal() as db:
        admin_ids = list(await db.scalars(select(User.id).where(User.role == Role.ADMIN, User.is_active.is_(True))))
        await db.execute(update(User).where(User.id.in_(admin_ids)).values(is_active=False))
        await db.commit()
    try:
        assert (await client.get(f"{API}/setup/status")).json() == {"needs_setup": True}

        # валидация
        assert (await client.post(f"{API}/setup", json={**BODY, "password": "short"})).status_code == 422
        assert (await client.post(f"{API}/setup", json={**BODY, "login": "1001"})).status_code == 409  # логин занят

        r = await client.post(f"{API}/setup", json={**BODY, "load_examples": True})
        assert r.status_code == 201, r.text
        pair = r.json()
        assert pair["user"]["role"] == "admin" and pair["access_token"]
        # сразу работает как админ
        hdr = {"Authorization": f"Bearer {pair['access_token']}"}
        assert (await client.get(f"{API}/users", headers=hdr)).status_code == 200

        # повторно настроить систему уже нельзя
        assert (await client.get(f"{API}/setup/status")).json() == {"needs_setup": False}
        assert (await client.post(f"{API}/setup", json={**BODY, "login": "intruder"})).status_code == 409

        # примеры справочников не задублировались (участки уже были)
        async with SessionLocal() as db:
            names = list(await db.scalars(select(Workshop.name)))
        assert len(names) == len(set(names))
    finally:
        async with SessionLocal() as db:
            await db.execute(update(User).where(User.id.in_(admin_ids)).values(is_active=True))
            await db.execute(update(User).where(User.login == "first-admin").values(is_active=False))
            await db.commit()
