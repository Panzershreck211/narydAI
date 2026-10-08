"""Регистрация и управление сотрудниками, справочники, права доступа."""

API = "/api/v1"


async def test_registration_full_cycle(client, h):
    admin = await h("admin")
    body = {
        "login": "reg-1",
        "password": "Secret#123",
        "fio": "Ковалёв Денис Игоревич",
        "role": "master",
        "specialty": "Мастер смены",
        "shift": "night",
    }
    r = await client.post(f"{API}/users", json=body, headers=admin)
    assert r.status_code == 201, r.text
    user = r.json()
    assert user["role"] == "master" and user["has_pin"] is False and user["is_active"] is True

    # новый мастер сразу входит и получает свои права
    r = await client.post(f"{API}/auth/login", json={"login": "reg-1", "password": "Secret#123"})
    assert r.status_code == 200
    master = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(f"{API}/orders/board", headers=master)).status_code == 200
    assert (await client.post(f"{API}/users", json=body, headers=master)).status_code == 403

    # смена роли администратором применяется к следующему запросу
    r = await client.patch(f"{API}/users/{user['id']}", json={"role": "manager"}, headers=admin)
    assert r.json()["role"] == "manager"
    assert (await client.post(f"{API}/orders", json={}, headers=master)).status_code == 403


async def test_registration_validation(client, h):
    admin = await h("admin")
    ok = {"login": "reg-2", "password": "Secret#123", "fio": "Иванов И.И.", "role": "executor"}
    bad_cases = [
        {**ok, "password": "short"},  # пароль < 8
        {**ok, "login": "логин"},  # только латиница
        {**ok, "pin": "12"},  # ПИН 4–6 цифр
        {**ok, "grade": 9},  # разряд 1–6
        {**ok, "role": "boss"},  # неизвестная роль
        {**ok, "brigade_id": 99999},  # нет такой бригады
    ]
    for case in bad_cases:
        r = await client.post(f"{API}/users", json=case, headers=admin)
        assert r.status_code == 422, (case, r.text)


async def test_block_and_restore_user(client, h):
    admin = await h("admin")
    r = await client.post(
        f"{API}/users",
        json={"login": "reg-3", "password": "Secret#123", "pin": "2468", "fio": "Блоков Б.Б.", "role": "executor"},
        headers=admin,
    )
    uid = r.json()["id"]
    pair = (await client.post(f"{API}/auth/pin-login", json={"login": "reg-3", "pin": "2468"})).json()
    worker = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.get(f"{API}/auth/me", headers=worker)).status_code == 200

    assert (await client.delete(f"{API}/users/{uid}", headers=admin)).status_code == 204
    # уже выданные токены перестают работать сразу
    assert (await client.get(f"{API}/auth/me", headers=worker)).status_code == 401
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 401

    # заблокированный виден администратору (для восстановления)
    users = (await client.get(f"{API}/users", headers=admin)).json()
    assert any(u["id"] == uid and not u["is_active"] for u in users)
    active_only = (await client.get(f"{API}/users", params={"active": True}, headers=admin)).json()
    assert all(u["id"] != uid for u in active_only)

    await client.patch(f"{API}/users/{uid}", json={"is_active": True}, headers=admin)
    assert (await client.post(f"{API}/auth/pin-login", json={"login": "reg-3", "pin": "2468"})).status_code == 200


async def test_admin_cannot_lock_themselves_out(client, h, tokens):
    admin = await h("admin")
    me = (await tokens("admin"))["user"]["id"]
    assert (await client.patch(f"{API}/users/{me}", json={"role": "master"}, headers=admin)).status_code == 400
    assert (await client.patch(f"{API}/users/{me}", json={"is_active": False}, headers=admin)).status_code == 400
    assert (await client.delete(f"{API}/users/{me}", headers=admin)).status_code == 400


async def test_reset_password_unlocks_pin(client, h):
    admin = await h("admin")
    r = await client.post(
        f"{API}/users",
        json={"login": "reg-4", "password": "Secret#123", "pin": "1111", "fio": "Сбросов С.С.", "role": "executor"},
        headers=admin,
    )
    uid = r.json()["id"]
    for _ in range(5):
        await client.post(f"{API}/auth/pin-login", json={"login": "reg-4", "pin": "0000"})
    assert (await client.post(f"{API}/auth/pin-login", json={"login": "reg-4", "pin": "1111"})).status_code == 429

    r = await client.post(f"{API}/users/{uid}/reset-password", json={"password": "NewPass#2026", "pin": "9999"}, headers=admin)
    assert r.status_code == 204
    assert (await client.post(f"{API}/auth/pin-login", json={"login": "reg-4", "pin": "9999"})).status_code == 200
    assert (await client.post(f"{API}/auth/login", json={"login": "reg-4", "password": "NewPass#2026"})).status_code == 200
    assert (await client.post(f"{API}/auth/login", json={"login": "reg-4", "password": "Secret#123"})).status_code == 401


async def test_user_sets_own_pin(client):
    pair = (await client.post(f"{API}/auth/login", json={"login": "boss", "password": "Boss#2026"})).json()
    hdr = {"Authorization": f"Bearer {pair['access_token']}"}
    assert (await client.post(f"{API}/auth/me/pin", json={"pin": "4321", "password": "wrong"}, headers=hdr)).status_code == 403
    assert (await client.post(f"{API}/auth/me/pin", json={"pin": "4321", "password": "Boss#2026"}, headers=hdr)).status_code == 204
    assert (await client.post(f"{API}/auth/pin-login", json={"login": "boss", "pin": "4321"})).status_code == 200


async def test_references_crud(client, h):
    admin, master = await h("admin"), await h("master1")

    r = await client.post(f"{API}/refs/workshops", json={"name": "Цех тестовый"}, headers=admin)
    assert r.status_code == 201
    ws = r.json()
    assert (await client.post(f"{API}/refs/workshops", json={"name": "Цех тестовый"}, headers=admin)).status_code == 409
    assert (await client.post(f"{API}/refs/workshops", json={"name": "X"}, headers=master)).status_code == 403

    eq = (
        await client.post(
            f"{API}/refs/equipment",
            json={"name": "Насос тест", "inventory_number": "T-1", "workshop_id": ws["id"], "criticality": "C"},
            headers=admin,
        )
    ).json()
    filtered = (await client.get(f"{API}/refs/equipment", params={"workshop_id": ws["id"]}, headers=master)).json()
    assert [e["id"] for e in filtered] == [eq["id"]]

    r = await client.put(
        f"{API}/refs/equipment/{eq['id']}",
        json={"name": "Насос тест-2", "inventory_number": "T-1", "workshop_id": ws["id"], "criticality": "A"},
        headers=admin,
    )
    assert r.json()["criticality"] == "A"

    # нельзя удалить участок, пока на нём есть оборудование
    assert (await client.delete(f"{API}/refs/workshops/{ws['id']}", headers=admin)).status_code == 409
    assert (await client.delete(f"{API}/refs/equipment/{eq['id']}", headers=admin)).status_code == 204
    assert (await client.delete(f"{API}/refs/workshops/{ws['id']}", headers=admin)).status_code == 204
    assert (await client.delete(f"{API}/refs/workshops/{ws['id']}", headers=admin)).status_code == 404


async def test_references_validation(client, h):
    admin = await h("admin")
    cases = [
        ("fault-codes", {"code": "Z-1", "name": "x", "category": "magic"}),
        ("materials", {"name": "Болт", "unit": "шт", "max_per_order": -1}),
        ("equipment", {"name": "x", "inventory_number": "Q", "workshop_id": 1, "criticality": "Z"}),
    ]
    for path, body in cases:
        assert (await client.post(f"{API}/refs/{path}", json=body, headers=admin)).status_code == 422, path


async def test_master_marks_shift(client, h, new_executor):
    master = await h("master1")
    ex = await new_executor()

    def status_of(items):
        return next(x["availability"] for x in items if x["id"] == ex["id"])

    avail = (await client.get(f"{API}/users/executors/availability", headers=master)).json()
    assert status_of(avail) == "free"
    await client.patch(f"{API}/users/{ex['id']}/shift", json={"on_shift": False}, headers=master)
    avail = (await client.get(f"{API}/users/executors/availability", headers=master)).json()
    assert status_of(avail) == "off_shift"
    # исполнитель не может менять смену другим
    assert (await client.patch(f"{API}/users/{ex['id']}/shift", json={"on_shift": True}, headers=ex["h"])).status_code == 403
    # но может себе
    assert (await client.patch(f"{API}/users/me/shift", json={"on_shift": True}, headers=ex["h"])).json()["on_shift"]


async def test_admin_creates_another_admin(client, h):
    admin = await h("admin")
    r = await client.post(
        f"{API}/users",
        json={"login": "admin2", "password": "Admin2#2026", "fio": "Второй Администратор", "role": "admin"},
        headers=admin,
    )
    assert r.status_code == 201 and r.json()["role"] == "admin"

    pair = (await client.post(f"{API}/auth/login", json={"login": "admin2", "password": "Admin2#2026"})).json()
    admin2 = {"Authorization": f"Bearer {pair['access_token']}"}
    # новый админ имеет полные права: регистрирует сотрудников и ведёт справочники
    r = await client.post(
        f"{API}/users",
        json={"login": "by-admin2", "password": "Secret#123", "fio": "Новичков Н.Н.", "role": "executor"},
        headers=admin2,
    )
    assert r.status_code == 201
    assert (await client.post(f"{API}/refs/brigades", json={"name": "Бригада №9"}, headers=admin2)).status_code == 201
    # и может заблокировать демо-учётку admin, когда она больше не нужна
    first_admin_id = (await client.get(f"{API}/auth/me", headers=admin)).json()["id"]
    assert (await client.patch(f"{API}/users/{first_admin_id}", json={"grade": None}, headers=admin2)).status_code == 200


async def test_create_admin_command(client, h):
    import pytest

    from app.create_admin import create_admin

    user, created = await create_admin("boot-admin", "Первый Администратор", "FirstAdmin#1")
    assert created and user.role.value == "admin"
    r = await client.post(f"{API}/auth/login", json={"login": "boot-admin", "password": "FirstAdmin#1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"

    # повторный запуск для того же логина = восстановление доступа
    _, created = await create_admin("boot-admin", None, "Recovered#2")
    assert not created
    assert (await client.post(f"{API}/auth/login", json={"login": "boot-admin", "password": "Recovered#2"})).status_code == 200
    assert (await client.post(f"{API}/auth/login", json={"login": "boot-admin", "password": "FirstAdmin#1"})).status_code == 401

    # восстановление заодно повышает до админа и снимает блокировку
    admin = await h("admin")
    uid = (
        await client.post(
            f"{API}/users",
            json={"login": "reg-6", "password": "Secret#123", "fio": "Повышаев П.П.", "role": "executor"},
            headers=admin,
        )
    ).json()["id"]
    await client.delete(f"{API}/users/{uid}", headers=admin)
    await create_admin("reg-6", None, "Promoted#33")
    me = (await client.post(f"{API}/auth/login", json={"login": "reg-6", "password": "Promoted#33"})).json()["user"]
    assert me["role"] == "admin" and me["is_active"]

    for login, fio, pwd in [("ab", "Иванов", "Password#1"), ("new-x", "Иванов", "short"), ("new-y", None, "Password#1")]:
        with pytest.raises(ValueError):
            await create_admin(login, fio, pwd)


async def test_connection_settings_for_phone(client, h, monkeypatch):
    from app.core.config import settings

    # IP передаёт скрипт запуска; повторы и пробелы отбрасываются
    monkeypatch.setattr(settings, "server_lan_ips", " 192.168.1.5,10.0.0.7, 192.168.1.5 ,")
    monkeypatch.setattr(settings, "web_port", 9080)
    r = await client.get(f"{API}/settings/connection", headers=await h("admin"))
    assert r.status_code == 200, r.text
    assert r.json() == {"lan_ips": ["192.168.1.5", "10.0.0.7"], "web_port": 9080}

    monkeypatch.setattr(settings, "server_lan_ips", "")
    assert (await client.get(f"{API}/settings/connection", headers=await h("admin"))).json()["lan_ips"] == []

    # адрес сети видит только администратор
    for login in ("master1", "boss", "1001"):
        assert (await client.get(f"{API}/settings/connection", headers=await h(login))).status_code == 403
    assert (await client.get(f"{API}/settings/connection")).status_code == 401
