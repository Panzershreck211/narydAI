"""Регрессии по итогам QA-ревью: секрет JWT, фото-«бомбы», PATCH с null, пагинация, часовой пояс."""

import io
from datetime import timedelta

from PIL import Image

from app.core.config import settings
from app.core.security import create_token, decode_token, ensure_jwt_secret
from app.db.base import plant_time, utcnow
from app.db.session import SessionLocal
from app.models import Notification, WorkOrder
from app.services.ai.deadline_monitor import check_deadlines
from app.services.ai.photo_checker import _parse_exif_dt

API = "/api/v1"


async def test_jwt_secret_is_generated_once_per_install(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    async with SessionLocal() as db:
        await ensure_jwt_secret(db)
    first = settings.jwt_secret
    assert len(first) == 64 and first != "change-me-in-production-please-32+chars"

    # перезапуск API: ключ берётся из БД, а не генерируется заново — токены остаются валидными
    token = create_token(1, "admin", "access")
    monkeypatch.setattr(settings, "jwt_secret", "replace-with-64-random-chars")
    async with SessionLocal() as db:
        await ensure_jwt_secret(db)
    assert settings.jwt_secret == first
    assert decode_token(token, "access")["sub"] == "1"


def test_weak_jwt_secret_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "change-me-in-production-please-32+chars")
    try:
        create_token(1, "admin", "access")
    except RuntimeError as e:
        assert "JWT_SECRET" in str(e)
    else:
        raise AssertionError("токен подписан общеизвестным ключом")


async def test_decompression_bomb_is_rejected(client, h, order_payload):
    master = await h("master1")
    o = (await client.post(f"{API}/orders", json=await order_payload("1001"), headers=master)).json()
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, "PNG")  # 81 Мп, а файл — десятки КБ
    r = await client.post(
        f"{API}/orders/{o['id']}/photos",
        params={"type": "before"},
        files=[("files", ("bomb.png", buf.getvalue(), "image/png"))],
        headers=master,
    )
    assert r.status_code == 422
    assert "разрешение" in r.json()["detail"]
    assert (settings.media_dir / "orders" / str(o["id"])).exists()
    assert not any((settings.media_dir / "orders" / str(o["id"])).iterdir())  # файл удалён


async def test_patch_rejects_null_for_required_fields(client, h, order_payload):
    master, admin = await h("master1"), await h("admin")
    o = (await client.post(f"{API}/orders", json=await order_payload("1001"), headers=master)).json()
    for body in ({"description": None}, {"priority": None}, {"equipment_stopped": None}):
        r = await client.patch(f"{API}/orders/{o['id']}", json=body, headers=master)
        assert r.status_code == 422, body
    # необязательное поле очистить можно
    r = await client.patch(f"{API}/orders/{o['id']}", json={"equipment_id": None}, headers=master)
    assert r.status_code == 200 and r.json()["equipment"] is None

    uid = (await client.get(f"{API}/auth/me", headers=master)).json()["id"]
    for body in ({"fio": None}, {"role": None}, {"is_active": None}):
        assert (await client.patch(f"{API}/users/{uid}", json=body, headers=admin)).status_code == 422, body


async def test_negative_pagination_is_422(client, h):
    master = await h("master1")
    assert (await client.get(f"{API}/orders", params={"limit": -1}, headers=master)).status_code == 422
    assert (await client.get(f"{API}/orders", params={"offset": -1}, headers=master)).status_code == 422
    assert (await client.get(f"{API}/notifications", params={"limit": 0}, headers=master)).status_code == 422


async def test_notification_shows_plant_local_time(client, h, order_payload, new_executor):
    master, ex = await h("master1"), await new_executor()
    deadline = (utcnow() + timedelta(hours=3)).replace(second=0, microsecond=0)
    await client.post(
        f"{API}/orders",
        json=await order_payload(None, executor_id=ex["id"], deadline=deadline.isoformat()),
        headers=master,
    )
    note = (await client.get(f"{API}/notifications", headers=ex["h"])).json()[0]
    assert f"срок {plant_time(deadline)}" in note["body"]
    assert "UTC" not in note["body"]


def test_exif_time_uses_plant_offset_or_exif_offset():
    # камера пишет местное время без пояса — это время предприятия, а не UTC
    assert _parse_exif_dt("2026:10:05 10:15:00").endswith(f"+{settings.plant_utc_offset_hours:02d}:00")
    assert _parse_exif_dt("2026:10:05 10:15:00", "+03:00") == "2026-10-05T10:15:00+03:00"


async def test_rejected_order_alerts_masters_not_the_rejecter(client, h, order_payload, new_executor):
    master, ex = await h("master1"), await new_executor()
    o = (await client.post(f"{API}/orders", json=await order_payload(None, executor_id=ex["id"]), headers=master)).json()
    r = await client.post(f"{API}/orders/{o['id']}/actions/reject", json={"reason": "Нет допуска"}, headers=ex["h"])
    assert r.json()["status"] == "rejected"

    async with SessionLocal() as db:
        row = await db.get(WorkOrder, o["id"])
        row.deadline = utcnow() - timedelta(minutes=1)
        await db.commit()
        await check_deadlines(db)
        overdue = (
            await db.execute(
                Notification.__table__.select().where(Notification.order_id == o["id"], Notification.kind == "overdue")
            )
        ).all()
    recipients = {n.user_id for n in overdue}
    assert ex["id"] not in recipients
    assert recipients  # мастер(а) узнали, что отклонённый наряд просрочен
