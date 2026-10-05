"""ИИ-помощник: инструменты с учётом ролей, цикл вызова инструментов, ключ в панели, SSE.

Сеть не нужна: клиент Claude подменяется фейком с заранее заданными ответами.
"""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User
from app.services.ai import assistant

API = "/api/v1"


# ---------- фейковый клиент Claude ----------


class FakeStream:
    def __init__(self, texts: list[str], content: list, stop_reason: str):
        self._texts = texts
        self._final = SimpleNamespace(content=content, stop_reason=stop_reason)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for t in self._texts:
                yield SimpleNamespace(type="text", text=t)

        return gen()

    async def get_final_message(self):
        return self._final


class FakeClient:
    """Отдаёт заранее заготовленные ходы и запоминает, что ему прислали."""

    def __init__(self, turns: list[FakeStream]):
        self.turns = list(turns)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return self.turns.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def tool_use(name: str, args: dict, id_: str = "tu_1"):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=args)


def text_block(t: str):
    return SimpleNamespace(type="text", text=t)


async def get_user(login: str) -> User:
    async with SessionLocal() as db:
        return await db.scalar(select(User).where(User.login == login))


async def collect(user_login: str, question: str, client: FakeClient) -> list[dict]:
    async with SessionLocal() as db:
        me = await db.scalar(select(User).where(User.login == user_login))
        msgs = [assistant.ChatMessage(role="user", content=question)]
        return [e async for e in assistant.chat(db, me, msgs, "sk-test", client_factory=lambda _k: client)]


# ---------- инструменты ----------


async def test_tools_respect_roles(client, h, order_payload, new_executor):
    master = await h("master1")
    ex = await new_executor()
    other = await new_executor()
    mine = (await client.post(f"{API}/orders", json=await order_payload(None, executor_id=ex["id"]), headers=master)).json()
    theirs = (await client.post(f"{API}/orders", json=await order_payload(None, executor_id=other["id"]), headers=master)).json()

    async with SessionLocal() as db:
        me = await db.get(User, ex["id"])
        tb = assistant.Toolbox(db, me)
        found = json.loads((await tb.run("find_orders", {}))[0])
        numbers = {o["number"] for o in found["orders"]}
        assert mine["number"] in numbers and theirs["number"] not in numbers

        own, err = await tb.run("order_details", {"number": mine["number"]})
        assert not err and json.loads(own)["number"] == mine["number"]
        foreign = json.loads((await tb.run("order_details", {"number": theirs["number"]}))[0])
        assert "error" in foreign  # чужой наряд не раскрывается

        for staff_only in ("executors_status", "executor_ratings", "equipment_downtime"):
            _, is_error = await tb.run(staff_only, {})
            assert is_error, staff_only

        summary = json.loads((await tb.run("shift_summary", {}))[0])
        assert summary["мои_открытые"] >= 1

    async with SessionLocal() as db:
        boss = await db.scalar(select(User).where(User.login == "boss"))
        tb = assistant.Toolbox(db, boss)
        status = json.loads((await tb.run("executors_status", {}))[0])
        assert any(e["fio"].startswith("Иванов") for e in status["executors"])
        assert "issued" in json.loads((await tb.run("shift_summary", {}))[0])
        rating, err = await tb.run("executor_ratings", {"days": 30})
        assert not err and "rating" in json.loads(rating)
        assert not (await tb.run("equipment_downtime", {"days": 7}))[1]


async def test_tool_input_validation():
    boss = await get_user("boss")
    async with SessionLocal() as db:
        tb = assistant.Toolbox(db, boss)
        for name, bad in [
            ("find_orders", {"status": ["flying"]}),
            ("find_orders", {"limit": 500}),
            ("executor_ratings", {"days": 0}),
            ("reference_lookup", {"kind": "passwords"}),
            ("order_details", "not-a-dict"),
            ("drop_database", {}),
        ]:
            _, is_error = await tb.run(name, bad)
            assert is_error, (name, bad)

        codes = json.loads((await tb.run("reference_lookup", {"kind": "fault_codes", "query": "подшип"}))[0])
        assert any("М-01" in c for c in codes["items"])


# ---------- цикл диалога ----------


async def test_chat_runs_tool_then_answers():
    fake = FakeClient(
        [
            FakeStream(["Сейчас посмотрю. "], [text_block("Сейчас посмотрю. "), tool_use("find_orders", {"overdue": True})], "tool_use"),
            FakeStream(["Просроченных ", "нарядов нет."], [text_block("Просроченных нарядов нет.")], "end_turn"),
        ]
    )
    events = await collect("master1", "Что просрочено?", fake)

    assert [e["type"] for e in events] == ["text", "tool", "text", "text", "done"]
    assert events[1]["label"] == "Ищу наряды"
    # второй запрос к модели содержит её ход без изменений и результат инструмента
    second = fake.calls[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["content"][1].name == "find_orders"
    result = second[-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu_1" and not result["is_error"]
    assert "found" in json.loads(result["content"])
    # параметры запроса: модель, низкое усилие, серверный fallback
    first = fake.calls[0]
    assert first["output_config"] == {"effort": "low"}
    assert first["fallbacks"] == "default"
    assert "Ахметов" in first["system"]  # знает, с кем говорит


async def test_chat_history_is_text_only_and_trimmed():
    fake = FakeClient([FakeStream(["Ок"], [text_block("Ок")], "end_turn")])
    boss = await get_user("boss")
    history = []
    for i in range(30):
        history.append(assistant.ChatMessage(role="user", content=f"вопрос {i}"))
        history.append(assistant.ChatMessage(role="assistant", content=f"ответ {i}"))
    history.append(assistant.ChatMessage(role="user", content="последний"))
    async with SessionLocal() as db:
        _ = [e async for e in assistant.chat(db, boss, history, "k", client_factory=lambda _k: fake)]
    sent = fake.calls[0]["messages"]
    assert len(sent) == 20 and sent[-1] == {"role": "user", "content": "последний"}
    assert all(isinstance(m["content"], str) for m in sent)


async def test_chat_refusal_and_loop_limit():
    events = await collect("boss", "x", FakeClient([FakeStream([], [], "refusal")]))
    assert events[-1]["type"] == "error"

    endless = [FakeStream([], [tool_use("shift_summary", {}, f"t{i}")], "tool_use") for i in range(assistant.MAX_TOOL_ROUNDS)]
    events = await collect("boss", "x", FakeClient(endless))
    assert sum(e["type"] == "tool" for e in events) == assistant.MAX_TOOL_ROUNDS
    assert events[-1]["type"] == "error"


async def test_chat_maps_api_errors():
    import anthropic
    import httpx2

    class Failing(FakeClient):
        def _stream(self, **kwargs):
            raise anthropic.AuthenticationError(
                "bad key",
                response=httpx2.Response(401, request=httpx2.Request("POST", "https://api.anthropic.com")),
                body=None,
            )

    events = await collect("boss", "x", Failing([]))
    assert events == [{"type": "error", "message": events[0]["message"]}]
    assert "Настройках" in events[0]["message"]


# ---------- ключ в панели и HTTP ----------


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Подменяет anthropic.AsyncAnthropic: проверка ключа и чат без сети."""
    import anthropic

    state = {"valid": {"sk-ant-api03-valid-key-1234567890"}, "chat": None}

    class FakeAsyncAnthropic:
        def __init__(self, api_key=None, **_):
            self.api_key = api_key

            async def retrieve(model_id):
                if self.api_key not in state["valid"]:
                    import httpx2

                    raise anthropic.AuthenticationError(
                        "invalid", response=httpx2.Response(401, request=httpx2.Request("GET", "https://x")), body=None
                    )
                return SimpleNamespace(id=model_id)

            self.models = SimpleNamespace(retrieve=retrieve)

        async def __aenter__(self):
            return state["chat"] or self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeAsyncAnthropic)
    return state


async def test_key_management_and_chat_endpoint(client, h, fake_anthropic):
    admin, master = await h("admin"), await h("master1")

    assert (await client.get(f"{API}/assistant/status", headers=master)).json() == {"configured": False}
    r = await client.post(f"{API}/assistant/chat", json={"messages": [{"role": "user", "content": "привет"}]}, headers=master)
    assert r.status_code == 503 and "Настройках" in r.json()["detail"]

    # только админ управляет ключом
    assert (await client.get(f"{API}/settings/assistant", headers=master)).status_code == 403
    assert (await client.put(f"{API}/settings/assistant", json={"api_key": "sk-ant-api03-valid-key-1234567890"}, headers=master)).status_code == 403

    r = await client.put(f"{API}/settings/assistant", json={"api_key": "sk-ant-api03-WRONG-key-0000000000"}, headers=admin)
    assert r.status_code == 422 and "не принят" in r.json()["detail"]

    r = await client.put(f"{API}/settings/assistant", json={"api_key": "  sk-ant-api03-valid-key-1234567890 "}, headers=admin)
    body = r.json()
    assert r.status_code == 200 and body["configured"] and body["source"] == "panel"
    assert body["key_hint"] == "sk-ant-api03…7890" and "valid-key" not in body["key_hint"]  # ключ целиком не отдаём
    assert (await client.get(f"{API}/assistant/status", headers=master)).json() == {"configured": True}

    # чат по SSE
    fake_anthropic["chat"] = FakeClient(
        [
            FakeStream([], [tool_use("executors_status", {})], "tool_use"),
            FakeStream(["Свободны: ", "Жумабаев."], [text_block("Свободны: Жумабаев.")], "end_turn"),
        ]
    )
    r = await client.post(f"{API}/assistant/chat", json={"messages": [{"role": "user", "content": "Кто свободен?"}]}, headers=master)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["tool", "text", "text", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Свободны: Жумабаев."

    # последнее сообщение должно быть от пользователя
    r = await client.post(f"{API}/assistant/chat", json={"messages": [{"role": "assistant", "content": "x"}]}, headers=master)
    assert r.status_code == 422

    assert (await client.delete(f"{API}/settings/assistant", headers=admin)).status_code == 204
    assert (await client.get(f"{API}/assistant/status", headers=master)).json() == {"configured": False}
