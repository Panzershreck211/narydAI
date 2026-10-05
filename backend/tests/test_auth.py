API = "/api/v1"


async def test_login_and_me(client, h):
    r = await client.post(f"{API}/auth/login", json={"login": "master1", "password": "wrong"})
    assert r.status_code == 401

    r = await client.get(f"{API}/auth/me", headers=await h("master1"))
    assert r.status_code == 200
    assert r.json()["role"] == "master"


async def test_pin_login_and_refresh(client):
    r = await client.post(f"{API}/auth/pin-login", json={"login": "1002", "pin": "2580"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "executor"

    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert r.status_code == 200
    # access-токен нельзя использовать как refresh
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": body["access_token"]})
    assert r.status_code == 401


async def test_pin_lockout(client):
    for _ in range(5):
        r = await client.post(f"{API}/auth/pin-login", json={"login": "1004", "pin": "0000"})
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/pin-login", json={"login": "1004", "pin": "2580"})
    assert r.status_code == 429


async def test_admin_registers_user_and_rbac(client, h):
    payload = {
        "login": "1050",
        "password": "Secret#123",
        "pin": "4321",
        "fio": "Новиков Павел Игоревич",
        "role": "executor",
        "specialty": "Слесарь-ремонтник",
        "grade": 3,
    }
    # только администратор
    for login in ("master1", "boss", "1001"):
        r = await client.post(f"{API}/users", json=payload, headers=await h(login))
        assert r.status_code == 403, login

    r = await client.post(f"{API}/users", json=payload, headers=await h("admin"))
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert r.json()["has_pin"] is True

    r = await client.post(f"{API}/users", json=payload, headers=await h("admin"))
    assert r.status_code == 409

    r = await client.patch(f"{API}/users/{uid}", json={"grade": 4}, headers=await h("admin"))
    assert r.json()["grade"] == 4

    r = await client.delete(f"{API}/users/{uid}", headers=await h("admin"))
    assert r.status_code == 204
    r = await client.post(f"{API}/auth/pin-login", json={"login": "1050", "pin": "4321"})
    assert r.status_code == 401


async def test_executor_cannot_manage(client, h, order_payload):
    hdr = await h("1001")
    assert (await client.post(f"{API}/orders", json=await order_payload(), headers=hdr)).status_code == 403
    assert (await client.get(f"{API}/orders/board", headers=hdr)).status_code == 403
    assert (await client.post(f"{API}/refs/workshops", json={"name": "X"}, headers=hdr)).status_code == 403
    assert (await client.get(f"{API}/refs/workshops", headers=hdr)).status_code == 200
    assert (await client.get(f"{API}/orders")).status_code == 401
