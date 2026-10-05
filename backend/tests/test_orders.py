from datetime import timedelta

from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models import Notification, WorkOrder
from app.services.ai.deadline_monitor import check_deadlines
from tests.conftest import image_bytes

API = "/api/v1"


async def act(client, hdr, oid, action, reason=None):
    body = {"reason": reason} if reason else None
    return await client.post(f"{API}/orders/{oid}/actions/{action}", json=body, headers=hdr)


async def upload(client, hdr, oid, kind, *seeds):
    files = [("files", (f"p{s}.jpg", image_bytes(s), "image/jpeg")) for s in seeds]
    return await client.post(f"{API}/orders/{oid}/photos", params={"type": kind}, files=files, headers=hdr)


async def test_full_emergency_flow(client, h, refs, order_payload):
    master, worker, other = await h("master1"), await h("1001"), await h("1002")

    r = await client.post(f"{API}/orders", json=await order_payload(type="emergency", priority="critical"), headers=master)
    assert r.status_code == 201, r.text
    order = r.json()
    oid = order["number"] and order["id"]
    assert order["number"].startswith("НР-")
    assert order["status"] == "issued"

    assert (await upload(client, master, oid, "before", 1)).status_code == 200

    # Исполнитель видит наряд и аварийное уведомление; чужой исполнитель — нет
    mine = (await client.get(f"{API}/orders", headers=worker)).json()
    assert oid in [o["id"] for o in mine]
    assert (await client.get(f"{API}/orders/{oid}", headers=other)).status_code == 404
    notes = (await client.get(f"{API}/notifications", headers=worker)).json()
    assert any(n["order_id"] == oid and n["is_emergency"] for n in notes)

    detail = (await client.get(f"{API}/orders/{oid}", headers=worker)).json()
    assert set(detail["allowed_actions"]) >= {"accept", "queue", "reject", "start"}

    assert (await act(client, worker, oid, "accept")).json()["status"] == "accepted"
    assert (await act(client, worker, oid, "accept")).status_code == 409
    assert (await act(client, worker, oid, "start")).json()["status"] == "in_progress"

    complete = {
        "work_report": "Заменён подшипник приводного барабана конвейера, выполнена смазка узла и проверка вибрации",
        "fault_code_id": next(f["id"] for f in refs["fault-codes"] if f["code"] == "М-01"),
        "materials": [
            {"material_id": next(m["id"] for m in refs["materials"] if m["sku"] == "SKF-22320"), "quantity": 1},
            {"material_id": next(m["id"] for m in refs["materials"] if m["sku"] == "LUB-L24"), "quantity": 0.5},
        ],
    }
    # Аварийный наряд без фото «после» закрыть нельзя
    r = await client.post(f"{API}/orders/{oid}/complete", json=complete, headers=worker)
    assert r.status_code == 422

    assert (await upload(client, worker, oid, "after", 4)).status_code == 200
    r = await client.post(f"{API}/orders/{oid}/complete", json=complete, headers=worker)
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "completed"
    assert len(done["materials"]) == 2
    ai = done["ai_report"]
    assert ai is not None and 1 <= ai["score"] <= 5
    assert ai["photo_score"] is not None
    assert any(c["name"] == "relevance" and c["severity"] == "ok" for c in ai["checks"])

    # Счётчики: оборудование в простое пока наряд не принят
    counters = (await client.get(f"{API}/dashboard/counters", headers=master)).json()
    assert counters["equipment_down"] >= 1

    # Приёмка мастером: исполнитель не может
    assert (await client.post(f"{API}/orders/{oid}/approve", json={"master_score": 5}, headers=worker)).status_code == 403
    r = await client.post(f"{API}/orders/{oid}/approve", json={"master_score": 5}, headers=master)
    assert r.json()["status"] == "closed"

    ratings = (await client.get(f"{API}/analytics/ratings", headers=await h("boss"))).json()
    me = next(x for x in ratings if x["fio"].startswith("Иванов"))
    assert me["closed"] >= 1 and me["points"] > 0 and me["on_time_pct"] == 100.0

    board = (await client.get(f"{API}/orders/board", headers=master)).json()
    assert [c["key"] for c in board] == ["issued", "accepted", "in_progress", "queued", "done", "overdue"]


async def test_emergency_preempts_planned(client, h, order_payload):
    master, worker = await h("master1"), await h("1003")
    planned = (await client.post(f"{API}/orders", json=await order_payload("1003"), headers=master)).json()
    second = (await client.post(f"{API}/orders", json=await order_payload("1003"), headers=master)).json()
    urgent = (
        await client.post(f"{API}/orders", json=await order_payload("1003", type="emergency"), headers=master)
    ).json()

    assert (await act(client, worker, planned["id"], "start")).status_code == 200
    # второй плановый не стартует, пока первый в работе
    assert (await act(client, worker, second["id"], "start")).status_code == 409
    # аварийный — стартует и ставит плановый на паузу
    assert (await act(client, worker, urgent["id"], "start")).status_code == 200
    paused = (await client.get(f"{API}/orders/{planned['id']}", headers=worker)).json()
    assert paused["status"] == "paused"
    assert "аварийный" in paused["events"][-1]["reason"]

    avail = (await client.get(f"{API}/users/executors/availability", headers=master)).json()
    me = next(a for a in avail if a["fio"].startswith("Петренко"))
    assert me["availability"] == "queued" and me["active_orders"] == 1


async def test_reject_and_reassign(client, h, order_payload, tokens):
    master, w1, w2 = await h("master1"), await h("1001"), await h("1002")
    o = (await client.post(f"{API}/orders", json=await order_payload("1001"), headers=master)).json()

    assert (await act(client, w1, o["id"], "reject")).status_code == 422  # без причины
    r = await act(client, w1, o["id"], "reject", "Нет допуска к работам на высоте")
    assert r.json()["status"] == "rejected"
    notes = (await client.get(f"{API}/notifications", headers=master)).json()
    assert any(n["order_id"] == o["id"] and "отклонён" in n["title"] for n in notes)

    uid2 = (await tokens("1002"))["user"]["id"]
    r = await client.post(f"{API}/orders/{o['id']}/reassign", json={"executor_id": uid2}, headers=master)
    assert r.status_code == 200 and r.json()["status"] == "issued"
    assert (await client.get(f"{API}/orders/{o['id']}", headers=w1)).status_code == 404
    assert (await client.get(f"{API}/orders/{o['id']}", headers=w2)).status_code == 200


async def test_brigade_order_is_claimed(client, h, order_payload, refs):
    master, w1, w2 = await h("master1"), await h("1001"), await h("1002")
    brigade = next(b for b in refs["brigades"] if "мех" in b["name"])
    o = (
        await client.post(f"{API}/orders", json=await order_payload(None, brigade_id=brigade["id"]), headers=master)
    ).json()
    assert o["executor"] is None

    assert o["id"] in [x["id"] for x in (await client.get(f"{API}/orders", headers=w1)).json()]
    r = await act(client, w2, o["id"], "accept")
    assert r.json()["executor"]["fio"].startswith("Жумабаев")
    assert o["id"] not in [x["id"] for x in (await client.get(f"{API}/orders", headers=w1)).json()]


async def test_deadline_monitor(client, h, order_payload):
    master = await h("master1")
    soon = (utcnow() + timedelta(minutes=20)).isoformat()
    o = (await client.post(f"{API}/orders", json=await order_payload("1002", deadline=soon), headers=master)).json()

    async with SessionLocal() as db:
        await check_deadlines(db)
        order = await db.get(WorkOrder, o["id"])
        assert order.reminder_sent and order.risk_notified and not order.overdue_notified

        order.deadline = utcnow() - timedelta(minutes=5)
        await db.commit()
        await check_deadlines(db)
        await db.refresh(order)
        assert order.overdue_notified

        kinds = {
            n.kind
            for n in (await db.execute(Notification.__table__.select().where(Notification.order_id == o["id"]))).all()
        }
        assert {"reminder", "risk", "overdue"} <= kinds

    overdue = (await client.get(f"{API}/orders", params={"overdue": True}, headers=master)).json()
    assert o["id"] in [x["id"] for x in overdue]


async def test_photo_validation(client, h, order_payload):
    master = await h("master1")
    o = (await client.post(f"{API}/orders", json=await order_payload("1001"), headers=master)).json()
    r = await client.post(
        f"{API}/orders/{o['id']}/photos",
        params={"type": "before"},
        files=[("files", ("x.jpg", b"not an image", "image/jpeg"))],
        headers=master,
    )
    assert r.status_code == 422
    r = await upload(client, master, o["id"], "before", 1, 2, 3, 4, 5, 6)
    assert r.status_code == 422  # больше 5
