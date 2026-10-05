"""Юнит-тесты без HTTP: права переходов, расчёты, WebSocket-рассылка, токены, фото."""

import io
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from PIL import Image

from app.core.config import settings
from app.core.security import create_token, decode_token, hash_secret, verify_secret
from app.models import User, WorkOrder
from app.models.enums import (
    Availability,
    Criticality,
    OrderStatus,
    OrderType,
    Priority,
    Role,
)
from app.services.ai import text
from app.services.ai.deadline_monitor import DEFAULT_DURATION, DurationModel
from app.services.ai.photo_checker import analyze_photo, assess_photos, hamming
from app.services.ai.rating import complexity, timeliness
from app.services.availability import classify
from app.services.realtime import ConnectionManager
from app.services.workflow import allowed_actions


def order(status=OrderStatus.ISSUED, executor_id=10, brigade_id=None, otype=OrderType.PLANNED, **kw):
    return WorkOrder(id=1, status=status, executor_id=executor_id, brigade_id=brigade_id, type=otype, **kw)


def user(role, uid=10, brigade_id=None):
    return User(id=uid, role=role, brigade_id=brigade_id)


# ---------- машина состояний ----------


@pytest.mark.parametrize(
    ("status", "role", "expected"),
    [
        (OrderStatus.ISSUED, Role.EXECUTOR, {"accept", "queue", "reject", "start"}),
        (OrderStatus.ACCEPTED, Role.EXECUTOR, {"queue", "reject", "start"}),
        (OrderStatus.QUEUED, Role.EXECUTOR, {"reject", "start"}),
        (OrderStatus.IN_PROGRESS, Role.EXECUTOR, {"pause", "complete"}),
        (OrderStatus.PAUSED, Role.EXECUTOR, {"start"}),
        (OrderStatus.COMPLETED, Role.EXECUTOR, set()),
        (OrderStatus.ISSUED, Role.MASTER, {"reassign", "cancel"}),
        (OrderStatus.IN_PROGRESS, Role.MASTER, {"cancel"}),
        (OrderStatus.COMPLETED, Role.MASTER, {"approve", "return", "cancel"}),
        (OrderStatus.REJECTED, Role.MASTER, {"reassign", "cancel"}),
        (OrderStatus.CLOSED, Role.MASTER, set()),
        (OrderStatus.CANCELLED, Role.ADMIN, set()),
        (OrderStatus.COMPLETED, Role.MANAGER, set()),
    ],
)
def test_allowed_actions_matrix(status, role, expected):
    assert set(allowed_actions(order(status), user(role))) == expected


def test_executor_sees_actions_only_on_own_or_brigade_orders():
    assert allowed_actions(order(executor_id=99), user(Role.EXECUTOR)) == []
    brigade_order = order(executor_id=None, brigade_id=5)
    assert "accept" in allowed_actions(brigade_order, user(Role.EXECUTOR, brigade_id=5))
    assert allowed_actions(brigade_order, user(Role.EXECUTOR, brigade_id=6)) == []


def test_overdue_rules():
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    past, future = now - timedelta(minutes=1), now + timedelta(minutes=1)
    assert order(deadline=past).overdue_at(now)
    assert not order(deadline=future).overdue_at(now)
    assert not order(OrderStatus.CLOSED, deadline=past).overdue_at(now)
    assert not order(OrderStatus.CANCELLED, deadline=past).overdue_at(now)
    # исполнен в срок, а сейчас уже позже срока — не просрочен
    assert not order(OrderStatus.COMPLETED, deadline=past, completed_at=past - timedelta(minutes=5)).overdue_at(now)
    assert order(OrderStatus.COMPLETED, deadline=past, completed_at=now).overdue_at(now)


# ---------- занятость ----------


@pytest.mark.parametrize(
    ("on_shift", "active", "waiting", "expected"),
    [
        (False, 2, 3, Availability.OFF_SHIFT),
        (True, 0, 0, Availability.FREE),
        (True, 1, 0, Availability.BUSY),
        (True, 0, 2, Availability.QUEUED),
        (True, 1, 2, Availability.QUEUED),
    ],
)
def test_availability_colors(on_shift, active, waiting, expected):
    assert classify(on_shift, active, waiting) == expected


# ---------- рейтинг ----------


def test_complexity_weights():
    assert complexity(OrderType.PLANNED, Priority.LOW, None) == 1.0
    assert complexity(OrderType.EMERGENCY, Priority.CRITICAL, Criticality.A) == pytest.approx(3.0 * 1.5 * 1.5)
    assert complexity(OrderType.PLANNED, Priority.HIGH, Criticality.A) > complexity(OrderType.PLANNED, Priority.HIGH, Criticality.C)


def test_timeliness():
    d = datetime(2026, 1, 1, tzinfo=UTC)
    assert timeliness(d - timedelta(hours=1), d) == 1.0
    assert timeliness(d + timedelta(hours=24), d) == pytest.approx(0.5)
    assert timeliness(d + timedelta(days=10), d) == 0.3  # не ниже 0.3


# ---------- прогноз длительности ----------


def test_duration_model_fallbacks():
    h = timedelta(hours=1)
    rows = [(7, 1, OrderType.PLANNED, h), (7, 1, OrderType.PLANNED, 3 * h), (7, 1, OrderType.PLANNED, 2 * h)]
    rows += [(None, 2, OrderType.EMERGENCY, 30 * timedelta(minutes=1))] * 3
    model = DurationModel(rows)
    assert model.predict(order(equipment_id=7, workshop_id=1)) == 2 * h  # медиана по оборудованию
    assert model.predict(order(equipment_id=8, workshop_id=2, otype=OrderType.EMERGENCY)) == timedelta(minutes=30)
    # мало истории — норматив
    assert model.predict(order(equipment_id=9, workshop_id=3)) == DEFAULT_DURATION[OrderType.PLANNED]


# ---------- смены ----------


def test_current_shift_start():
    from app.api.v1.dashboard import current_shift_start

    off = settings.plant_utc_offset_hours
    local = lambda h, d=5: datetime(2026, 10, d, h, 30, tzinfo=UTC) - timedelta(hours=off)  # noqa: E731
    day_start = datetime(2026, 10, 5, 8, tzinfo=UTC) - timedelta(hours=off)
    night_start = datetime(2026, 10, 5, 20, tzinfo=UTC) - timedelta(hours=off)
    assert current_shift_start(local(9)) == day_start
    assert current_shift_start(local(21)) == night_start
    # 03:30 ночи — смена началась вчера в 20:00
    assert current_shift_start(local(3, d=6)) == night_start


# ---------- WebSocket-рассылка ----------


class FakeWS:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, msg):
        self.sent.append(msg)


async def test_broadcast_targets():
    m = ConnectionManager()
    master, other_worker, assignee, brigade_mate = FakeWS(), FakeWS(), FakeWS(), FakeWS()
    await m.connect(master, 1, Role.MASTER, None)
    await m.connect(other_worker, 2, Role.EXECUTOR, 9)
    await m.connect(assignee, 3, Role.EXECUTOR, 5)
    await m.connect(brigade_mate, 4, Role.EXECUTOR, 5)

    await m.broadcast_order({"type": "order_changed"}, executor_id=3, brigade_id=5)
    assert [len(w.sent) for w in (master, other_worker, assignee, brigade_mate)] == [1, 0, 1, 0]

    # наряд на бригаду, ещё не взят — видят все в бригаде
    await m.broadcast_order({"type": "order_changed"}, executor_id=None, brigade_id=5)
    assert [len(w.sent) for w in (master, other_worker, assignee, brigade_mate)] == [2, 0, 2, 1]

    m.disconnect(master, 1)
    await m.send_to_users({1, 3}, {"type": "notification"})
    assert len(master.sent) == 2 and len(assignee.sent) == 3


async def test_broadcast_survives_broken_socket():
    class Broken(FakeWS):
        async def send_json(self, msg):
            raise RuntimeError("closed")

    m = ConnectionManager()
    good = FakeWS()
    await m.connect(Broken(), 1, Role.MASTER, None)
    await m.connect(good, 2, Role.MASTER, None)
    await m.broadcast_order({"x": 1}, None, None)
    assert good.sent == [{"x": 1}]


# ---------- токены и пароли ----------


def test_tokens():
    access = create_token(5, "master", "access")
    assert decode_token(access, "access")["sub"] == "5"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(access, "refresh")  # access нельзя использовать как refresh
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(jwt.encode({"sub": "5", "type": "access"}, "чужой-ключ-длиной-больше-32-байт!!", algorithm="HS256"), "access")
    expired = jwt.encode(
        {"sub": "5", "type": "access", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired, "access")


def test_password_hashing():
    h = hash_secret("Пароль#1")
    assert h != "Пароль#1" and verify_secret("Пароль#1", h)
    assert not verify_secret("пароль#1", h)
    assert not verify_secret("x", None)
    assert not verify_secret("x", "not-a-bcrypt-hash")


# ---------- текст и фото ----------


def test_text_helpers():
    assert text.overlap("Течь масла из-под сальника насоса", "Заменён сальник насоса, течь устранена") > 0.5
    assert text.overlap("Течь масла", "Подтянуты клеммы") == 0
    hits = text.category_hits("Замена кабеля и автомата, проверка изоляции")
    assert max(hits, key=hits.get).value == "electrical"
    assert text.mentions_replacement("Заменил подшипник")


def test_photo_analysis_reads_exif(tmp_path):
    img = Image.new("RGB", (400, 300), (120, 120, 120))
    for x in range(0, 400, 10):
        for y in range(300):
            img.putpixel((x, y), (0, 0, 0))
    exif = Image.Exif()
    exif[271] = "Samsung"  # Make
    exif[272] = "SM-A546"  # Model
    exif[306] = "2026:10:05 10:15:00"  # DateTime
    path = tmp_path / "p.jpg"
    img.save(path, exif=exif)

    meta = analyze_photo(path)
    assert meta["has_exif"] and meta["camera"] == "Samsung SM-A546"
    assert meta["taken_at"].startswith("2026-10-05T10:15")
    assert meta["sharpness"] > 60 and len(meta["dhash"]) == 16

    # снимок «после» сделан раньше выдачи наряда — штраф
    pc = assess_photos([], [meta], datetime(2026, 10, 6, tzinfo=UTC))
    assert any("раньше выдачи" in i for i in pc.issues)


def test_photo_without_after_scores_minimum():
    assert assess_photos([], [], datetime.now(UTC)).score == 1.0
    assert hamming("ffff", "fff0") == 4


def test_blank_image_is_flagged_as_blurry(tmp_path):
    path = tmp_path / "blank.png"
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (10, 10, 10)).save(buf, "PNG")
    path.write_bytes(buf.getvalue())
    meta = analyze_photo(path)
    pc = assess_photos([], [meta], datetime.now(UTC))
    assert any("размыто" in i for i in pc.issues)
    assert any("EXIF" in i for i in pc.issues)
    assert pc.score <= 3


