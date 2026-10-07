import io
import os
import tempfile
from datetime import timedelta
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="naryad_test_"))
# По умолчанию — SQLite. Прогон на PostgreSQL: TEST_DATABASE_URL=postgresql+asyncpg://... (БД будет очищена!)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_tmp / "media")
os.environ["AI_MONITOR_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app.db.base import Base, utcnow  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

PASSWORDS = {"admin": "Admin#2026", "master1": "Master#2026", "boss": "Boss#2026"}

if engine.dialect.name == "sqlite":
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_fk(dbapi_conn, _):
        # Как в PostgreSQL: нарушение внешнего ключа — ошибка
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await seed()
    yield
    await engine.dispose()


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(scope="session")
async def tokens(client):
    cache: dict[str, dict] = {}

    async def get(login: str) -> dict:
        if login not in cache:
            r = await client.post(
                "/api/v1/auth/login", json={"login": login, "password": PASSWORDS.get(login, "Worker#2026")}
            )
            assert r.status_code == 200, r.text
            cache[login] = r.json()
        return cache[login]

    return get


@pytest.fixture(scope="session")
async def h(tokens):
    """h('master1') -> заголовки авторизации."""

    async def headers(login: str) -> dict:
        return {"Authorization": f"Bearer {(await tokens(login))['access_token']}"}

    return headers


@pytest.fixture(scope="session")
async def refs(client, h):
    hdr = await h("admin")
    out = {}
    for name in ("workshops", "equipment", "fault-codes", "materials", "brigades"):
        r = await client.get(f"/api/v1/refs/{name}", headers=hdr)
        out[name] = r.json()
    return out


@pytest.fixture
def order_payload(refs, tokens):
    async def make(executor_login: str | None = "1001", **overrides) -> dict:
        eq = next(e for e in refs["equipment"] if e["name"].startswith("Конвейер"))
        payload = {
            "type": "planned",
            "description": "Конвейер К-12: вибрация и шум приводного барабана, нагрев подшипника",
            "workshop_id": eq["workshop_id"],
            "equipment_id": eq["id"],
            "priority": "high",
            "deadline": (utcnow() + timedelta(hours=4)).isoformat(),
            "equipment_stopped": True,
        }
        if executor_login:
            payload["executor_id"] = (await tokens(executor_login))["user"]["id"]
        payload.update(overrides)
        return payload

    return make


def image_bytes(seed: int, fmt: str = "JPEG") -> bytes:
    img = Image.new("RGB", (320, 240), (40 + seed * 30 % 200, 90, 120))
    d = ImageDraw.Draw(img)
    for i in range(0, 320, 16 + seed):
        d.line([(i, 0), (320 - i, 240)], fill=(255, 255 - seed * 20 % 255, 0), width=3)
    d.ellipse([60 + seed * 10, 40, 200, 180 - seed * 5], outline=(0, 0, 0), width=5)
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


_seq = 0


@pytest.fixture
async def new_executor(client, h):
    """Регистрирует отдельного исполнителя на смене — тесты не делят наряды с сид-данными."""

    async def make(brigade_id: int | None = None) -> dict:
        global _seq
        _seq += 1
        admin = await h("admin")
        login = f"t{_seq:03d}"
        r = await client.post(
            "/api/v1/users",
            json={
                "login": login,
                "password": "Worker#2026",
                "pin": "1357",
                "fio": f"Тестов Исполнитель {_seq}",
                "role": "executor",
                "specialty": "Слесарь-ремонтник",
                "grade": 4,
                "brigade_id": brigade_id,
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text
        user = r.json()
        await client.patch(f"/api/v1/users/{user['id']}/shift", json={"on_shift": True}, headers=admin)
        tok = await client.post("/api/v1/auth/pin-login", json={"login": login, "pin": "1357"})
        return {"id": user["id"], "login": login, "h": {"Authorization": f"Bearer {tok.json()['access_token']}"}}

    return make
