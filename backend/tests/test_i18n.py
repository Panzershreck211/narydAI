"""Язык ответов: русские ошибки вместо английских Pydantic/FastAPI и казахский перевод по Accept-Language."""

import ast
import pathlib
import re

import pytest

from app.core.i18n import pick_lang, tr, validation_message
from app.services.ai.assistant import system_prompt
from app.services.realtime import ConnectionManager

API = "/api/v1"
KK = {"Accept-Language": "kk"}
APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def _error_texts() -> list[str]:
    """Все тексты из HTTPException(...) и ValueError(...) в коде; в f-строках подстановки → «7»."""
    out = []
    for path in APP.rglob("*.py"):
        if path.name == "create_admin.py":  # консольная утилита для сервера — только по-русски
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("HTTPException", "ValueError")):
                continue
            for arg in [*node.args, *(k.value for k in node.keywords if k.arg == "detail")]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.append(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    out.append("".join(v.value if isinstance(v, ast.Constant) else "7" for v in arg.values))
    return [t for t in out if re.search("[а-яё]", t, re.I)]


@pytest.mark.parametrize("text", _error_texts())
def test_every_error_message_has_kazakh_translation(text):
    if "«7»" in text:  # фото «до»/«после» и поля — подстановка не число, проверено ниже
        pytest.skip("шаблон с подстановкой-словом")
    assert tr(text, "kk") != text, f"нет перевода в app/core/i18n_kk.py: {text!r}"


@pytest.mark.parametrize(
    "ru",
    [
        "Нельзя выполнить «Начать» из статуса «Исполнен»",
        "Не больше 5 фото «после»",
        "«до»: 2 шт.",
        "Поля не могут быть пустыми: Описание, Срок",
        "Замечания: Не указан шифр неисправности; Фото «после» размыто или слишком мелкое",
        "Оценка 3.4/5. Замечания: Не указан шифр неисправности",
        "Насос течёт · приоритет критический · срок 07.10 18:00",
        "Шифр «М-01» (механика) не согласуется с текстом отчёта (по тексту — электрика)",
        "Просрочен на 39 ч 34 мин",
        "Иванов И.И.. ИИ-проверка: нужна проверка (3.4/5)",
    ],
)
def test_templates_translate_with_inner_phrases(ru):
    kk = tr(ru, "kk")
    assert kk != ru
    # вложенные фразы сервера тоже переведены — русских служебных слов не осталось
    for word in ("Исполнен", "Начать", "Не указан", "размыто", "критический", "механика»", "нужна проверка", "Описание"):
        assert word not in kk, (word, kk)


def test_human_text_is_not_translated():
    # описание проблемы написал человек — переводится только служебная часть
    assert tr("Течь масла · приоритет высокий · срок 07.10 18:00", "kk").startswith("Течь масла · басымдық: жоғары")
    assert tr("Нет допуска к работам на высоте", "kk") == "Нет допуска к работам на высоте"


def test_pick_lang():
    assert pick_lang("kk") == "kk" and pick_lang("kk-KZ,ru;q=0.8") == "kk" and pick_lang("kz") == "kk"
    assert pick_lang(None) == "ru" and pick_lang("en-US,en;q=0.9") == "ru" and pick_lang("ru-RU") == "ru"


def test_validation_messages_are_russian_with_field_labels():
    err = {"type": "string_too_short", "loc": ("body", "password"), "msg": "String should...", "ctx": {"min_length": 8}}
    assert validation_message(err, "ru") == "Пароль: не короче 8 симв."
    assert validation_message(err, "kk") == "Құпиясөз: кемінде 8 таңба"
    assert validation_message({"type": "missing", "loc": ("body", "fio")}, "ru") == "ФИО: обязательное поле"


async def test_api_errors_are_never_english(client, h):
    r = await client.post(f"{API}/auth/login", json={})
    assert r.status_code == 422
    assert [e["msg"] for e in r.json()["detail"]] == ["Логин: обязательное поле", "Пароль: обязательное поле"]

    assert (await client.get(f"{API}/orders")).json()["detail"] == "Требуется вход в систему"
    assert (await client.get(f"{API}/no-such-route")).json()["detail"] == "Не найдено"
    assert (await client.get(f"{API}/orders", headers=KK)).json()["detail"] == "Жүйеге кіру қажет"

    master = await h("master1")
    r = await client.get(f"{API}/orders/abc", headers=master)
    assert r.json()["detail"][0]["msg"] == "Наряд: нужно целое число"
    r = await client.get(f"{API}/orders/999999", headers={**master, **KK})
    assert r.json()["detail"] == "Наряд табылмады"


async def test_server_texts_follow_interface_language(client, h, order_payload, new_executor):
    master, ex = await h("master1"), await new_executor()
    o = (await client.post(f"{API}/orders", json=await order_payload(None, executor_id=ex["id"]), headers=master)).json()

    ru = (await client.get(f"{API}/notifications", headers=ex["h"])).json()[0]
    kk = (await client.get(f"{API}/notifications", headers={**ex["h"], **KK})).json()[0]
    assert ru["title"].startswith("Новый наряд") and kk["title"].startswith("Жаңа наряд")
    assert "басымдық: жоғары" in kk["body"]

    r = await client.post(f"{API}/orders/{o['id']}/actions/reject", json={"reason": "Нет допуска"}, headers=ex["h"])
    assert r.status_code == 200
    r = await client.post(f"{API}/orders/{o['id']}/actions/start", headers={**ex["h"], **KK})
    assert r.status_code == 409
    assert r.json()["detail"] == "«Бас тартылды» мәртебесінен «Бастау» әрекетін орындауға болмайды"

    board = (await client.get(f"{API}/orders/board", headers={**master, **KK})).json()
    assert [c["title"] for c in board][:2] == ["Мерзімі өткендер", "Берілгендер"]


class FakeWS:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, msg):
        self.sent.append(msg)


async def test_websocket_notifications_use_socket_language():
    from app.core.i18n import use_lang

    m = ConnectionManager()
    ru_ws, kk_ws = FakeWS(), FakeWS()
    await m.connect(ru_ws, 1, "executor", None)
    with use_lang("kk"):
        await m.connect(kk_ws, 1, "executor", None)
    await m.send_to_users({1}, {"type": "notification", "notification": {"title": "Риск просрочки: НР-1", "body": "Нет фото «после»"}})
    assert ru_ws.sent[0]["notification"]["title"] == "Риск просрочки: НР-1"
    assert kk_ws.sent[0]["notification"] == {"title": "Мерзімі өту қаупі: НР-1", "body": "«Кейін» фотосы жоқ"}


def test_assistant_answers_in_interface_language():
    from datetime import UTC, datetime

    from app.models import User
    from app.models.enums import Role

    u = User(id=1, fio="Тест", role=Role.MASTER)
    assert "по-казахски" in system_prompt(u, datetime.now(UTC), "kk")
    assert "по-русски" in system_prompt(u, datetime.now(UTC), "ru")
