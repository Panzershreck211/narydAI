"""Дополнительные сценарии жизненного цикла наряда и уведомлений."""

from datetime import timedelta

from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models import WorkOrder
from tests.conftest import image_bytes

API = "/api/v1"


async def act(client, hdr, oid, action, reason=None):
    return await client.post(f"{API}/orders/{oid}/actions/{action}", json={"reason": reason} if reason else None, headers=hdr)


async def make_order(client, master, order_payload, executor, **kw):
    r = await client.post(f"{API}/orders", json=await order_payload(None, executor_id=executor["id"], **kw), headers=master)
    assert r.status_code == 201, r.text
    return r.json()


async def complete(client, worker, oid, refs, report=None):
    body = {
        "work_report": report or "Заменён подшипник приводного барабана конвейера, выполнена смазка и проверка вибрации",
        "fault_code_id": next(f["id"] for f in refs["fault-codes"] if f["code"] == "М-01"),
        "materials": [{"material_name": "Ветошь", "quantity": 2, "unit": "кг"}],
    }
    return await client.post(f"{API}/orders/{oid}/complete", json=body, headers=worker)


async def test_create_validation(client, h, order_payload, refs, new_executor):
    master = await h("master1")
    ex = await new_executor()
    other_ws_eq = next(e for e in refs["equipment"] if e["name"].startswith("Экскаватор"))
    cases = [
        {"deadline": (utcnow() - timedelta(hours=1)).isoformat()},  # срок в прошлом
        {"deadline": "2030-01-01T10:00:00"},  # без часового пояса
        {"equipment_id": other_ws_eq["id"]},  # оборудование с другого участка
        {"executor_id": None},  # нет исполнителя и бригады
        {"executor_id": (await client.get(f"{API}/auth/me", headers=master)).json()["id"]},  # мастер — не исполнитель
        {"description": "abc"},  # слишком короткое
    ]
    for override in cases:
        payload = await order_payload(None, executor_id=ex["id"])
        payload.update(override)
        r = await client.post(f"{API}/orders", json=payload, headers=master)
        assert r.status_code == 422, (override, r.text)


async def test_pause_resume_and_queue(client, h, order_payload, new_executor):
    master = await h("master1")
    ex = await new_executor()
    o1 = await make_order(client, master, order_payload, ex)
    o2 = await make_order(client, master, order_payload, ex)

    assert (await act(client, ex["h"], o2["id"], "queue")).json()["status"] == "queued"
    assert (await act(client, ex["h"], o1["id"], "start")).json()["status"] == "in_progress"
    assert (await act(client, ex["h"], o1["id"], "pause")).status_code == 422  # без причины
    r = await act(client, ex["h"], o1["id"], "pause", "Ждём запчасть со склада")
    assert r.json()["status"] == "paused"
    # после паузы можно начать другой наряд, а потом вернуться
    assert (await act(client, ex["h"], o2["id"], "start")).json()["status"] == "in_progress"
    assert (await act(client, ex["h"], o1["id"], "start")).status_code == 409
    await act(client, ex["h"], o2["id"], "pause", "Обед")
    d = (await act(client, ex["h"], o1["id"], "start")).json()
    assert d["status"] == "in_progress"
    assert [e["action"] for e in d["events"]] == ["create", "start", "pause", "start"]


async def test_return_for_rework(client, h, order_payload, refs, new_executor):
    master = await h("master1")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)
    await act(client, ex["h"], o["id"], "start")
    assert (await complete(client, ex["h"], o["id"], refs)).json()["status"] == "completed"

    assert (await act(client, master, o["id"], "return")).status_code == 422
    r = await act(client, master, o["id"], "return", "Не устранена вибрация, повторить центровку")
    d = r.json()
    assert d["status"] == "in_progress" and d["completed_at"] is None

    notes = (await client.get(f"{API}/notifications", headers=ex["h"])).json()
    assert any(n["order_id"] == o["id"] and "доработку" in n["title"] for n in notes)

    # повторное закрытие — новый ИИ-отчёт
    d = (await complete(client, ex["h"], o["id"], refs)).json()
    assert d["status"] == "completed"
    ai_events = [e for e in d["events"] if e["action"] == "ai_check"]
    assert len(ai_events) == 2


async def test_cancel(client, h, order_payload, new_executor):
    master = await h("master1")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)
    assert (await act(client, ex["h"], o["id"], "cancel", "x")).status_code == 403
    assert (await act(client, master, o["id"], "cancel")).status_code == 422
    assert (await act(client, master, o["id"], "cancel", "Выдан ошибочно")).json()["status"] == "cancelled"
    assert (await act(client, ex["h"], o["id"], "start")).status_code == 409
    notes = (await client.get(f"{API}/notifications", headers=ex["h"])).json()
    assert any(n["order_id"] == o["id"] and "отменён" in n["title"] for n in notes)


async def test_edit_order(client, h, order_payload, refs, new_executor):
    master = await h("master1")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)

    async with SessionLocal() as db:
        row = await db.get(WorkOrder, o["id"])
        row.reminder_sent = row.risk_notified = True
        await db.commit()

    new_deadline = (utcnow() + timedelta(hours=10)).isoformat()
    r = await client.patch(f"{API}/orders/{o['id']}", json={"priority": "critical", "deadline": new_deadline}, headers=master)
    assert r.status_code == 200 and r.json()["priority"] == "critical"
    async with SessionLocal() as db:
        row = await db.get(WorkOrder, o["id"])
        # новый срок — ИИ-напоминания пойдут заново
        assert not row.reminder_sent and not row.risk_notified

    assert (await client.patch(f"{API}/orders/{o['id']}", json={"priority": "low"}, headers=ex["h"])).status_code == 403
    await act(client, ex["h"], o["id"], "start")
    await complete(client, ex["h"], o["id"], refs)
    assert (await client.patch(f"{API}/orders/{o['id']}", json={"priority": "low"}, headers=master)).status_code == 409


async def test_complete_validation(client, h, order_payload, refs, new_executor):
    master = await h("master1")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)
    # закрыть можно только из «в работе»
    assert (await complete(client, ex["h"], o["id"], refs)).status_code == 409
    await act(client, ex["h"], o["id"], "start")
    fault = next(f["id"] for f in refs["fault-codes"] if f["code"] == "М-01")
    bad = [
        {"work_report": "ok", "fault_code_id": 99999},
        {"work_report": "Заменён подшипник", "fault_code_id": fault, "materials": [{"quantity": 1}]},
        {"work_report": "Заменён подшипник", "fault_code_id": fault, "materials": [{"material_id": 99999, "quantity": 1}]},
        {"work_report": "Заменён подшипник", "fault_code_id": fault, "materials": [{"material_name": "x", "quantity": 0}]},
    ]
    for body in bad:
        r = await client.post(f"{API}/orders/{o['id']}/complete", json=body, headers=ex["h"])
        assert r.status_code == 422, (body, r.text)
    # чужой исполнитель не может закрыть
    other = await new_executor()
    assert (await complete(client, other["h"], o["id"], refs)).status_code == 404


async def test_weak_report_flagged_by_ai(client, h, order_payload, refs, new_executor):
    master = await h("master1")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)
    await act(client, ex["h"], o["id"], "start")
    d = (await complete(client, ex["h"], o["id"], refs, report="Сделал")).json()
    assert d["ai_report"]["verdict"] == "rejected"
    names = {c["name"] for c in d["ai_report"]["checks"] if c["severity"] in ("warn", "error")}
    assert {"completeness", "relevance", "duration"} <= names
    # мастер видит вердикт в уведомлении
    notes = (await client.get(f"{API}/notifications", headers=master)).json()
    assert any(n["order_id"] == o["id"] and "есть нарушения" in n["body"] for n in notes)


async def test_ai_recheck(client, h, order_payload, refs, new_executor):
    master, boss = await h("master1"), await h("boss")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)
    assert (await client.post(f"{API}/orders/{o['id']}/ai-check", headers=master)).status_code == 409
    await act(client, ex["h"], o["id"], "start")
    await complete(client, ex["h"], o["id"], refs)
    assert (await client.post(f"{API}/orders/{o['id']}/ai-check", headers=ex["h"])).status_code == 403
    d = (await client.post(f"{API}/orders/{o['id']}/ai-check", headers=boss)).json()
    assert sum(e["action"] == "ai_check" for e in d["events"]) == 2


async def test_manager_is_read_only(client, h, order_payload, refs, new_executor):
    master, boss = await h("master1"), await h("boss")
    ex = await new_executor()
    o = await make_order(client, master, order_payload, ex)
    d = (await client.get(f"{API}/orders/{o['id']}", headers=boss)).json()
    assert d["allowed_actions"] == []
    assert (await act(client, boss, o["id"], "cancel", "x")).status_code == 403
    assert (await client.post(f"{API}/orders", json=await order_payload("1001"), headers=boss)).status_code == 403
    r = await client.post(
        f"{API}/orders/{o['id']}/photos",
        params={"type": "before"},
        files=[("files", ("a.jpg", image_bytes(1), "image/jpeg"))],
        headers=boss,
    )
    assert r.status_code == 403


async def test_notifications_read(client, h, order_payload, new_executor):
    master = await h("master1")
    ex = await new_executor()
    await make_order(client, master, order_payload, ex, type="emergency")
    await make_order(client, master, order_payload, ex)

    notes = (await client.get(f"{API}/notifications", params={"unread_only": True}, headers=ex["h"])).json()
    assert len(notes) == 2 and notes[0]["created_at"] >= notes[1]["created_at"]
    assert sum(n["is_emergency"] for n in notes) == 1

    assert (await client.post(f"{API}/notifications/{notes[0]['id']}/read", headers=ex["h"])).status_code == 204
    # чужое уведомление прочитать нельзя
    assert (await client.post(f"{API}/notifications/{notes[1]['id']}/read", headers=master)).status_code == 404
    assert len((await client.get(f"{API}/notifications", params={"unread_only": True}, headers=ex["h"])).json()) == 1
    await client.post(f"{API}/notifications/read-all", headers=ex["h"])
    assert (await client.get(f"{API}/notifications", params={"unread_only": True}, headers=ex["h"])).json() == []


async def test_orders_filters(client, h, order_payload, new_executor):
    master = await h("master1")
    ex = await new_executor()
    e = await make_order(client, master, order_payload, ex, type="emergency")
    p = await make_order(client, master, order_payload, ex)
    await act(client, ex["h"], p["id"], "queue")

    ids = lambda r: [o["id"] for o in r.json()]  # noqa: E731
    r = await client.get(f"{API}/orders", params={"executor_id": ex["id"]}, headers=master)
    assert ids(r)[0] == e["id"]  # аварийные — первыми
    r = await client.get(f"{API}/orders", params={"executor_id": ex["id"], "type": "planned"}, headers=master)
    assert ids(r) == [p["id"]]
    r = await client.get(f"{API}/orders", params=[("executor_id", ex["id"]), ("status", "queued"), ("status", "issued")], headers=master)
    assert set(ids(r)) == {e["id"], p["id"]}
    r = await client.get(f"{API}/orders", params={"executor_id": ex["id"], "status": "closed"}, headers=master)
    assert ids(r) == []


async def test_dashboard_and_downtime(client, h, order_payload, refs, new_executor):
    master, boss = await h("master1"), await h("boss")
    ex = await new_executor()
    before = (await client.get(f"{API}/dashboard/counters", headers=boss)).json()
    o = await make_order(client, master, order_payload, ex, equipment_stopped=True)
    await act(client, ex["h"], o["id"], "start")
    after = (await client.get(f"{API}/dashboard/counters", headers=boss)).json()
    assert after["issued"] == before["issued"] + 1
    assert after["in_progress"] == before["in_progress"] + 1

    rows = (await client.get(f"{API}/analytics/downtime", headers=boss)).json()
    conveyor = next(r for r in rows if r["equipment"].startswith("Конвейер"))
    assert conveyor["still_down"] is True and conveyor["orders"] >= 1
    assert (await client.get(f"{API}/analytics/downtime", headers=ex["h"])).status_code == 403
    assert (await client.get(f"{API}/dashboard/counters", headers=ex["h"])).status_code == 403
