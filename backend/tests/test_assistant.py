"""ИИ-помощник: инструменты с учётом ролей, цикл вызова функций Gemini, ключ в панели, SSE.

Сеть не нужна: Gemini API подменяется фейковым сервером на httpx.MockTransport.
"""

import json

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import User
from app.services.ai import assistant, gemini, llm_judge

API = "/api/v1"
VALID_KEY = "AIzaSy-valid-test-key-1234567890"


# ---------- фейковый Gemini API ----------


def text(t: str, **extra) -> dict:
    return {"text": t, **extra}


def call(name: str, args: dict | None = None, id_: str | None = None) -> dict:
    fc = {"name": name, "args": args or {}}
    if id_:
        fc["id"] = id_
    return {"functionCall": fc, "thoughtSignature": "sig-" + name}


def turn(*chunks: list[dict], finish: str = "STOP") -> list[dict]:
    """Ход модели: несколько SSE-событий, в последнем — причина остановки."""
    events = [{"candidates": [{"content": {"role": "model", "parts": parts}}]} for parts in chunks]
    if not events:
        events = [{"candidates": [{"content": {"role": "model", "parts": []}}]}]
    events[-1]["candidates"][0]["finishReason"] = finish
    return events


class FakeGemini:
    """Отдаёт заготовленные ходы и запоминает запросы."""

    def __init__(self, turns: list[list[dict]] | None = None, *, status: int = 200, generate: dict | None = None):
        self.turns = list(turns or [])
        self.status = status
        self.generate_response = generate
        self.requests: list[dict] = []
        self.keys: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.keys.append(request.headers.get("x-goog-api-key", ""))
        path = request.url.path
        if request.method == "GET" and path.endswith(f"/models/{settings.llm_model}"):
            if request.headers.get("x-goog-api-key") != VALID_KEY:
                return httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API_KEY_INVALID"}})
            return httpx.Response(200, json={"name": f"models/{settings.llm_model}"})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": self.status, "status": "RESOURCE_EXHAUSTED"}})
        body = json.loads(request.content)
        self.requests.append(body)
        if path.endswith(":generateContent"):
            return httpx.Response(200, json=self.generate_response)
        assert path.endswith(":streamGenerateContent") and request.url.params["alt"] == "sse"
        sse = "".join(f"data: {json.dumps(e, ensure_ascii=False)}\r\n\r\n" for e in self.turns.pop(0))
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    def factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=settings.gemini_base_url, transport=httpx.MockTransport(self.handler))


async def get_user(login: str) -> User:
    async with SessionLocal() as db:
        return await db.scalar(select(User).where(User.login == login))


async def collect(user_login: str, question: str, fake: FakeGemini) -> list[dict]:
    async with SessionLocal() as db:
        me = await db.scalar(select(User).where(User.login == user_login))
        msgs = [assistant.ChatMessage(role="user", content=question)]
        return [e async for e in assistant.chat(db, me, msgs, VALID_KEY, client_factory=fake.factory)]


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



def test_function_declarations_fit_gemini():
    """Схемы инструментов — подмножество OpenAPI: без $ref, anyOf, title; без параметров — без схемы."""
    blob = json.dumps(assistant.FUNCTIONS)
    assert "$ref" not in blob and "anyOf" not in blob and '"title"' not in blob and "additionalProperties" not in blob
    by_name = {f["name"]: f for f in assistant.FUNCTIONS}
    assert "parameters" not in by_name["shift_summary"]
    status = by_name["find_orders"]["parameters"]["properties"]["status"]
    assert status["type"] == "array" and "in_progress" in status["items"]["enum"] and status["nullable"]


# ---------- цикл диалога ----------


async def test_chat_runs_function_then_answers():
    fake = FakeGemini(
        [
            turn([text("Сейчас посмотрю. ")], [call("find_orders", {"overdue": True}, "c1")]),
            turn([text("Просроченных ")], [text("нарядов нет.")]),
        ]
    )
    events = await collect("master1", "Что просрочено?", fake)

    assert [e["type"] for e in events] == ["text", "tool", "text", "text", "done"]
    assert events[1]["label"] == "Ищу наряды"
    assert fake.keys[0] == VALID_KEY  # ключ — в заголовке, не в URL
    # второй запрос содержит ход модели без изменений (с подписью) и результат функции
    second = fake.requests[1]["contents"]
    assert second[-2]["role"] == "model" and second[-2]["parts"][1]["thoughtSignature"] == "sig-find_orders"
    result = second[-1]["parts"][0]["functionResponse"]
    assert second[-1]["role"] == "user" and result["name"] == "find_orders" and result["id"] == "c1"
    assert "found" in result["response"]["result"]
    first = fake.requests[0]
    assert "Ахметов" in first["systemInstruction"]["parts"][0]["text"]  # знает, с кем говорит
    assert first["tools"][0]["functionDeclarations"] == assistant.FUNCTIONS


async def test_chat_reports_tool_errors_to_model():
    fake = FakeGemini([turn([call("executors_status")]), turn([text("Нет доступа.")])])
    events = await collect("1001", "Кто свободен?", fake)  # исполнителю аналитика недоступна
    assert events[-1]["type"] == "done"
    response = fake.requests[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]
    assert "error" in response and "id" not in fake.requests[1]["contents"][-1]["parts"][0]["functionResponse"]


async def test_chat_history_is_text_only_and_trimmed():
    fake = FakeGemini([turn([text("Ок")])])
    boss = await get_user("boss")
    history = []
    for i in range(30):
        history.append(assistant.ChatMessage(role="user", content=f"вопрос {i}"))
        history.append(assistant.ChatMessage(role="assistant", content=f"ответ {i}"))
    history.append(assistant.ChatMessage(role="user", content="последний"))
    async with SessionLocal() as db:
        _ = [e async for e in assistant.chat(db, boss, history, VALID_KEY, client_factory=fake.factory)]
    sent = fake.requests[0]["contents"]
    # последние 20 реплик без ведущего ответа помощника: диалог для Gemini начинается с пользователя
    assert len(sent) == 19 and sent[0]["role"] == "user"
    assert sent[-1] == {"role": "user", "parts": [{"text": "последний"}]}
    assert sent[-2]["role"] == "model"


async def test_long_history_and_long_answers_do_not_break_chat(client, h):
    """После длинного ответа помощника следующий вопрос не должен получать 422."""
    long_answer = "Длинный ответ. " * 600  # ~9000 символов
    history = []
    for i in range(30):
        history += [{"role": "user", "content": f"вопрос {i}"}, {"role": "assistant", "content": long_answer}]
    history.append({"role": "user", "content": "ещё вопрос"})
    master = await h("master1")
    r = await client.post(f"{API}/assistant/chat", json={"messages": history}, headers=master)
    assert r.status_code != 422, r.text  # 503 — ключ в тесте не задан, но валидация пройдена

    msg = assistant.ChatMessage(role="assistant", content=long_answer)
    assert len(msg.content) == assistant.MAX_MESSAGE + 1  # обрезан, «…» в конце
    r = await client.post(
        f"{API}/assistant/chat", json={"messages": [{"role": "user", "content": "x" * 5000}]}, headers=master
    )
    assert r.status_code == 422 and "Вопрос длиннее 4000 символов" in r.json()["detail"][0]["msg"]


async def test_chat_blocked_too_long_and_loop_limit():
    assert (await collect("boss", "x", FakeGemini([turn(finish="SAFETY")])))[-1]["type"] == "error"
    events = await collect("boss", "x", FakeGemini([turn([text("очень")], finish="MAX_TOKENS")]))
    assert events[-1] == {"type": "error", "message": "Ответ получился слишком длинным, уточните вопрос"}

    endless = [turn([call("shift_summary")]) for _ in range(assistant.MAX_TOOL_ROUNDS)]
    events = await collect("boss", "x", FakeGemini(endless))
    assert sum(e["type"] == "tool" for e in events) == assistant.MAX_TOOL_ROUNDS
    assert events[-1]["type"] == "error"


@pytest.mark.parametrize(
    ("status", "words"),
    [(429, "лимит бесплатного"), (403, "Настройках"), (503, "перегружен"), (400, "Ошибка ИИ-сервиса")],
)
async def test_chat_maps_api_errors(status, words):
    events = await collect("boss", "x", FakeGemini(status=status))
    assert len(events) == 1 and events[0]["type"] == "error" and words in events[0]["message"]


async def test_chat_network_error():
    def broken() -> httpx.AsyncClient:
        def fail(request):
            raise httpx.ConnectError("нет сети")

        return httpx.AsyncClient(base_url=settings.gemini_base_url, transport=httpx.MockTransport(fail))

    async with SessionLocal() as db:
        me = await db.scalar(select(User).where(User.login == "boss"))
        msgs = [assistant.ChatMessage(role="user", content="x")]
        events = [e async for e in assistant.chat(db, me, msgs, VALID_KEY, client_factory=broken)]
    assert events == [{"type": "error", "message": "Нет связи с ИИ-сервисом"}]


# ---------- смысловая проверка наряда ----------


FACTS = llm_judge.OrderFacts("Течь масла из редуктора", "Редуктор", "Г-02", "Заменил сальник, долил масло", ["Сальник 1 шт"])


async def test_judge_parses_structured_answer():
    answer = {"relevance": 7, "materials_logical": True, "issues": [], "summary": "Работа соответствует"}
    fake = FakeGemini(generate={"candidates": [{"content": {"parts": [text(json.dumps(answer, ensure_ascii=False))]}, "finishReason": "STOP"}]})
    verdict = await llm_judge.judge(FACTS, VALID_KEY, fake.factory)
    assert verdict and verdict.relevance == 5 and verdict.summary == "Работа соответствует"  # оценка обрезана до 5
    cfg = fake.requests[0]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json" and "relevance" in cfg["responseSchema"]["properties"]
    assert "<отчёт>" in fake.requests[0]["contents"][0]["parts"][0]["text"]


async def test_judge_failures_fall_back_to_rules():
    assert await llm_judge.judge(FACTS, None) is None
    assert await llm_judge.judge(FACTS, VALID_KEY, FakeGemini(status=429).factory) is None
    garbage = FakeGemini(generate={"candidates": [{"content": {"parts": [text("не json")]}, "finishReason": "STOP"}]})
    assert await llm_judge.judge(FACTS, VALID_KEY, garbage.factory) is None
    blocked = FakeGemini(generate={"promptFeedback": {"blockReason": "SAFETY"}})
    assert await llm_judge.judge(FACTS, VALID_KEY, blocked.factory) is None


def test_schema_conversion():
    schema = gemini.to_schema(llm_judge.LLMVerdict.model_json_schema())
    assert schema["type"] == "object" and schema["properties"]["issues"] == {"type": "array", "items": {"type": "string"}}
    assert "title" not in json.dumps(schema)


# ---------- ключ в панели и HTTP ----------


@pytest.fixture
def fake_gemini(monkeypatch):
    """Подменяет HTTP-клиент Gemini для всего приложения (проверка ключа и чат без сети)."""
    fake = FakeGemini()
    monkeypatch.setattr(gemini, "default_client", fake.factory)
    return fake


async def test_key_management_and_chat_endpoint(client, h, fake_gemini):
    admin, master = await h("admin"), await h("master1")

    assert (await client.get(f"{API}/assistant/status", headers=master)).json() == {"configured": False}
    r = await client.post(f"{API}/assistant/chat", json={"messages": [{"role": "user", "content": "привет"}]}, headers=master)
    assert r.status_code == 503 and "Настройках" in r.json()["detail"]

    # только админ управляет ключом
    assert (await client.get(f"{API}/settings/assistant", headers=master)).status_code == 403
    assert (await client.put(f"{API}/settings/assistant", json={"api_key": VALID_KEY}, headers=master)).status_code == 403

    r = await client.put(f"{API}/settings/assistant", json={"api_key": "AIzaSy-WRONG-key-00000000000000"}, headers=admin)
    assert r.status_code == 422 and "не принят" in r.json()["detail"]

    r = await client.put(f"{API}/settings/assistant", json={"api_key": f"  {VALID_KEY} "}, headers=admin)
    body = r.json()
    assert r.status_code == 200 and body["configured"] and body["source"] == "panel"
    assert body["model"] == settings.llm_model and body["model"].startswith("gemini")
    assert body["key_hint"] == "AIzaSy-v…7890" and "valid-test" not in body["key_hint"]  # ключ целиком не отдаём
    assert (await client.get(f"{API}/assistant/status", headers=master)).json() == {"configured": True}

    # чат по SSE
    fake_gemini.turns = [turn([call("executors_status")]), turn([text("Свободны: ")], [text("Жумабаев.")])]
    r = await client.post(f"{API}/assistant/chat", json={"messages": [{"role": "user", "content": "Кто свободен?"}]}, headers=master)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["tool", "text", "text", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Свободны: Жумабаев."

    # ошибка лимита — по-казахски, если интерфейс на казахском
    fake_gemini.status = 429
    r = await client.post(
        f"{API}/assistant/chat",
        json={"messages": [{"role": "user", "content": "x"}]},
        headers={**master, "Accept-Language": "kk"},
    )
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert events == [{"type": "error", "message": "Gemini тегін тарифінің шегі таусылды — бір минуттан кейін қайталаңыз"}]
    fake_gemini.status = 200

    # последнее сообщение должно быть от пользователя
    r = await client.post(f"{API}/assistant/chat", json={"messages": [{"role": "assistant", "content": "x"}]}, headers=master)
    assert r.status_code == 422

    assert (await client.delete(f"{API}/settings/assistant", headers=admin)).status_code == 204
    assert (await client.get(f"{API}/assistant/status", headers=master)).json() == {"configured": False}


async def test_overloaded_model_falls_back_to_next(monkeypatch):
    """Основная модель перегружена (503) — ответ даёт запасная, пользователь сбоя не видит."""
    monkeypatch.setattr(settings, "llm_model", "main-model")
    monkeypatch.setattr(settings, "llm_fallback_models", ["spare-model"])
    fake = FakeGemini([turn([text("Ответ запасной модели")])])
    handler = fake.handler
    used = []

    def by_model(request: httpx.Request) -> httpx.Response:
        used.append(request.url.path.rsplit("/", 1)[-1].split(":")[0])
        if "main-model" in request.url.path:
            return httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})
        return handler(request)

    fake.handler = by_model
    events = await collect("boss", "x", fake)
    assert used == ["main-model", "spare-model"]
    assert [e["type"] for e in events] == ["text", "done"]

    # ИИ-проверка наряда тоже переходит на запасную модель
    answer = {"relevance": 4, "materials_logical": True, "issues": [], "summary": "ок"}
    fake.generate_response = {"candidates": [{"content": {"parts": [text(json.dumps(answer))]}, "finishReason": "STOP"}]}
    used.clear()
    assert (await llm_judge.judge(FACTS, VALID_KEY, fake.factory)).summary == "ок"
    assert used == ["main-model", "spare-model"]
