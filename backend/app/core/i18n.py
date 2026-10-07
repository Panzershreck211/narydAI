"""Язык ответов API: русский (основной) и казахский.

Сервер хранит и формирует тексты на русском (уведомления, журнал наряда, ИИ-проверка, ошибки),
а переводит их только при выдаче — на язык, который клиент выбрал в интерфейсе
(заголовок Accept-Language: kk). Текст, который написали люди (описание проблемы, отчёт,
причина отказа), не переводится. Словарь — в app/core/i18n_kk.py.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated, Any, Literal

from pydantic import PlainSerializer

Lang = Literal["ru", "kk"]
LANGS: tuple[Lang, ...] = ("ru", "kk")

_lang: ContextVar[Lang] = ContextVar("lang", default="ru")


def pick_lang(value: str | None) -> Lang:
    """«kk», «kk-KZ», «kz» → kk; всё остальное (и пусто) → ru."""
    for part in (value or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith(("kk", "kz")):
            return "kk"
        if tag:
            return "ru"
    return "ru"


def get_lang() -> Lang:
    return _lang.get()


@contextmanager
def use_lang(lang: Lang) -> Iterator[None]:
    token = _lang.set(lang)
    try:
        yield
    finally:
        _lang.reset(token)


def tr(text: str | None, lang: Lang | None = None) -> str | None:
    """Перевод фразы, сформированной сервером. Незнакомый текст возвращается как есть."""
    from app.core.i18n_kk import KK, PATTERNS

    if not text or (lang or get_lang()) == "ru":
        return text
    if text in KK:
        return KK[text]
    for rx, template in PATTERNS:
        m = rx.fullmatch(text)
        if m:
            # группы с именем t_* — тоже фразы сервера (статус, вердикт…), их переводим
            parts = {k: _tr_group(k, v) for k, v in m.groupdict().items()}
            return template.format(**parts)
    return text


def _tr_group(name: str, value: str) -> str:
    if name == "t_list":  # «Замечания: a; b; c»
        return "; ".join(tr(x, "kk") or x for x in value.split("; "))
    if name == "t_fields":  # «Поля не могут быть пустыми: Описание, Срок»
        kk_by_ru = {ru: kk for ru, kk in FIELDS.values()}
        return ", ".join(kk_by_ru.get(x, x) for x in value.split(", "))
    return (tr(value, "kk") or value) if name.startswith("t_") else value


# Ответы самого FastAPI/Starlette приходят по-английски — заменяем на русские
FRAMEWORK_RU = {
    "Not authenticated": "Требуется вход в систему",
    "Not Found": "Не найдено",
    "Method Not Allowed": "Метод не поддерживается",
    "Internal Server Error": "Внутренняя ошибка сервера",
    "Too Many Requests": "Слишком много запросов",
}


# Поле схемы ответа с текстом сервера: сериализуется на языке запроса
Localized = Annotated[str, PlainSerializer(lambda v: tr(v), return_type=str, when_used="json")]


def _tr_checks(checks: list | None) -> list | None:
    if not checks:
        return checks
    return [{**c, "message": tr(c.get("message"))} if isinstance(c, dict) else c for c in checks]


LocalizedChecks = Annotated[list | None, PlainSerializer(_tr_checks, when_used="json")]


# ---------- ошибки валидации (Pydantic по умолчанию отвечает по-английски) ----------

FIELDS: dict[str, tuple[str, str]] = {
    "login": ("Логин", "Логин"),
    "password": ("Пароль", "Құпиясөз"),
    "pin": ("ПИН-код", "ПИН-код"),
    "fio": ("ФИО", "Аты-жөні"),
    "role": ("Роль", "Рөлі"),
    "specialty": ("Специальность", "Мамандығы"),
    "grade": ("Разряд", "Разряды"),
    "brigade_id": ("Бригада", "Бригада"),
    "shift": ("Смена", "Ауысым"),
    "on_shift": ("Смена", "Ауысым"),
    "is_active": ("Активен", "Белсенді"),
    "type": ("Тип", "Түрі"),
    "description": ("Описание", "Сипаттама"),
    "workshop_id": ("Участок", "Учаске"),
    "equipment_id": ("Оборудование", "Жабдық"),
    "executor_id": ("Исполнитель", "Орындаушы"),
    "priority": ("Приоритет", "Басымдық"),
    "deadline": ("Срок", "Мерзім"),
    "equipment_stopped": ("Оборудование остановлено", "Жабдық тоқтап тұр"),
    "work_report": ("Описание работ", "Жұмыс сипаттамасы"),
    "fault_code_id": ("Шифр неисправности", "Ақау шифры"),
    "materials": ("Материалы", "Материалдар"),
    "material_id": ("Материал", "Материал"),
    "material_name": ("Название материала", "Материал атауы"),
    "quantity": ("Количество", "Саны"),
    "reason": ("Причина", "Себебі"),
    "master_score": ("Оценка", "Баға"),
    "api_key": ("Ключ", "Кілт"),
    "name": ("Название", "Атауы"),
    "code": ("Код", "Коды"),
    "inventory_number": ("Инвентарный номер", "Инвентарлық нөмірі"),
    "criticality": ("Критичность", "Маңыздылығы"),
    "category": ("Категория", "Санаты"),
    "sku": ("Артикул", "Артикул"),
    "unit": ("Единица измерения", "Өлшем бірлігі"),
    "max_per_order": ("Максимум на наряд", "Бір нарядқа ең көбі"),
    "comment": ("Комментарий", "Түсініктеме"),
    "status": ("Статус", "Мәртебе"),
    "limit": ("Лимит", "Шек"),
    "offset": ("Смещение", "Ығысу"),
    "order_id": ("Наряд", "Наряд"),
    "user_id": ("Сотрудник", "Қызметкер"),
    "files": ("Файлы", "Файлдар"),
    "messages": ("Сообщения", "Хабарламалар"),
    "refresh_token": ("Токен", "Токен"),
    "fcm_token": ("Токен устройства", "Құрылғы токені"),
}

_MESSAGES: dict[str, tuple[str, str]] = {
    "missing": ("обязательное поле", "міндетті өріс"),
    "string_too_short": ("не короче {min_length} симв.", "кемінде {min_length} таңба"),
    "string_too_long": ("не длиннее {max_length} симв.", "{max_length} таңбадан аспауы керек"),
    "string_pattern_mismatch": ("недопустимый формат", "пішімі жарамсыз"),
    "string_type": ("нужен текст", "мәтін қажет"),
    "int_parsing": ("нужно целое число", "бүтін сан қажет"),
    "int_type": ("нужно целое число", "бүтін сан қажет"),
    "int_from_float": ("нужно целое число", "бүтін сан қажет"),
    "float_parsing": ("нужно число", "сан қажет"),
    "float_type": ("нужно число", "сан қажет"),
    "bool_parsing": ("нужно «да» или «нет»", "«иә» немесе «жоқ» қажет"),
    "bool_type": ("нужно «да» или «нет»", "«иә» немесе «жоқ» қажет"),
    "enum": ("недопустимое значение", "жарамсыз мән"),
    "literal_error": ("недопустимое значение", "жарамсыз мән"),
    "datetime_parsing": ("неверные дата и время", "күні мен уақыты қате"),
    "datetime_from_date_parsing": ("неверные дата и время", "күні мен уақыты қате"),
    "datetime_type": ("неверные дата и время", "күні мен уақыты қате"),
    "date_parsing": ("неверная дата", "күні қате"),
    "greater_than": ("должно быть больше {gt}", "{gt} мәнінен үлкен болуы керек"),
    "greater_than_equal": ("не меньше {ge}", "кемінде {ge}"),
    "less_than": ("должно быть меньше {lt}", "{lt} мәнінен кіші болуы керек"),
    "less_than_equal": ("не больше {le}", "{le} мәнінен аспауы керек"),
    "too_short": ("нужно не меньше {min_length} эл.", "кемінде {min_length} элемент"),
    "too_long": ("не больше {max_length} эл.", "{max_length} элементтен аспауы керек"),
    "list_type": ("нужен список", "тізім қажет"),
    "json_invalid": ("некорректный JSON в запросе", "сұраудағы JSON қате"),
}
_DEFAULT = ("некорректное значение", "мәні қате")


def field_label(name: str, lang: Lang | None = None) -> str:
    ru, kk = FIELDS.get(name, (name, name))
    return kk if (lang or get_lang()) == "kk" else ru


def validation_message(err: dict[str, Any], lang: Lang | None = None) -> str:
    """Одна ошибка Pydantic → «Пароль: не короче 8 симв.» на нужном языке."""
    lang = lang or get_lang()
    kind = err.get("type", "")
    if kind == "value_error":  # наши собственные сообщения из валидаторов — уже по-русски
        text = re.sub(r"^Value error, ", "", str(err.get("msg", "")))
        return tr(text, lang) or text
    ru, kk = _MESSAGES.get(kind, _DEFAULT)
    try:
        text = (kk if lang == "kk" else ru).format(**(err.get("ctx") or {}))
    except (KeyError, IndexError, ValueError):
        text = kk if lang == "kk" else ru
    names = [p for p in err.get("loc", ()) if isinstance(p, str) and p not in ("body", "query", "path", "header")]
    if kind == "json_invalid" or not names:
        return text[:1].upper() + text[1:]
    return f"{field_label(names[-1], lang)}: {text}"
