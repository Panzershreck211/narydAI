"""Лёгкая обработка русского текста без внешних NLP-библиотек."""

import re

from app.models.enums import FaultCategory

_WORD = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

STOP = {
    "было", "была", "были", "этот", "этого", "также", "после", "через", "который", "которая",
    "работы", "работа", "выполнен", "выполнено", "произведен", "произведена", "произведено",
    "проведен", "проведена", "согласно", "наряд", "наряду", "требуется", "необходимо",
}

# Ключевые основы слов по категориям неисправностей
CATEGORY_STEMS: dict[FaultCategory, tuple[str, ...]] = {
    FaultCategory.ELECTRICAL: (
        "элект", "кабел", "провод", "контак", "автом", "предох", "щит", "двига", "обмот",
        "напря", "замык", "пуска", "реле", "клемм", "изоля", "фаз", "ток",
    ),
    FaultCategory.MECHANICAL: (
        "подши", "вал", "муфт", "редук", "ремен", "ремн", "цеп", "болт", "звезд", "шестер",
        "вибра", "износ", "свар", "лент", "ролик", "бараб", "шкив", "крепл", "зубч",
    ),
    FaultCategory.HYDRAULIC: (
        "гидра", "масл", "насос", "шланг", "рукав", "цилин", "утечк", "течь", "давле",
        "клапа", "уплот", "сальн", "манже",
    ),
    FaultCategory.PNEUMATIC: ("пневм", "возду", "компр", "ресив", "пневмо"),
    FaultCategory.INSTRUMENTATION: ("датчи", "кипиа", "преоб", "манометр", "термо", "контрол", "сигна"),
    FaultCategory.LUBRICATION: ("смаз", "масле", "солид", "литол", "масл"),
}

REPLACEMENT_STEMS = ("замен", "устан", "смени", "смен", "монтир", "поставил", "заменил")


def stems(text: str) -> set[str]:
    words = (w.lower() for w in _WORD.findall(text or ""))
    return {w[:5] for w in words if len(w) >= 4 and w not in STOP}


def overlap(a: str, b: str) -> float:
    """Доля основ из `a`, встречающихся в `b` (0..1)."""
    sa, sb = stems(a), stems(b)
    if not sa:
        return 0.0
    return len(sa & sb) / len(sa)


def category_hits(text: str) -> dict[FaultCategory, int]:
    low = (text or "").lower()
    words = _WORD.findall(low)
    hits: dict[FaultCategory, int] = {}
    for cat, prefixes in CATEGORY_STEMS.items():
        n = sum(1 for w in words if w.startswith(prefixes))
        if n:
            hits[cat] = n
    return hits


def mentions_replacement(text: str) -> bool:
    low = (text or "").lower()
    return any(s in low for s in REPLACEMENT_STEMS)
