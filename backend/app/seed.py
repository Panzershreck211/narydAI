"""Демо-данные: python -m app.seed

Пароли ниже — только для локального стенда, после первого входа их нужно сменить.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_secret
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Brigade, Equipment, FaultCode, Material, User, Workshop
from app.models.enums import Criticality, FaultCategory, Role, Shift

F = FaultCategory

WORKSHOPS = {
    "Карьер": [("Экскаватор ЭКГ-10 №3", "КМ-0103", Criticality.A), ("Буровой станок СБШ-250", "КМ-0110", Criticality.B)],
    "Дробильно-сортировочная фабрика": [
        ("Конусная дробилка КСД-2200", "КМ-0201", Criticality.A),
        ("Конвейер ленточный К-12", "КМ-0212", Criticality.A),
        ("Грохот ГИЛ-52", "КМ-0220", Criticality.B),
    ],
    "Обогатительная фабрика №1": [
        ("Насос ГрАТ 1400/40", "КМ-0305", Criticality.B),
        ("Сепаратор пневматический СП-3", "КМ-0311", Criticality.B),
    ],
    "Энергоцех": [("Трансформаторная подстанция ТП-6", "КМ-0401", Criticality.A), ("Компрессор 4ВМ10", "КМ-0408", Criticality.C)],
}

FAULT_CODES = [
    ("М-01", "Износ/разрушение подшипника", F.MECHANICAL),
    ("М-02", "Порыв/сход конвейерной ленты", F.MECHANICAL),
    ("М-03", "Ослабление крепления, вибрация", F.MECHANICAL),
    ("Э-01", "Короткое замыкание", F.ELECTRICAL),
    ("Э-02", "Отказ электродвигателя", F.ELECTRICAL),
    ("Э-03", "Срабатывание защиты, автомат", F.ELECTRICAL),
    ("Г-01", "Утечка рабочей жидкости", F.HYDRAULIC),
    ("Г-02", "Отказ гидронасоса", F.HYDRAULIC),
    ("П-01", "Утечка воздуха, падение давления", F.PNEUMATIC),
    ("К-01", "Отказ датчика / КИПиА", F.INSTRUMENTATION),
    ("С-01", "Недостаточная смазка узла", F.LUBRICATION),
    ("Х-00", "Прочее", F.OTHER),
]

MATERIALS = [
    ("Подшипник 22320 CC/W33", "SKF-22320", "шт", F.MECHANICAL, 4),
    ("Лента конвейерная ЕР-400", "LNT-EP400", "м", F.MECHANICAL, 60),
    ("Болт М16х60 с гайкой", "BLT-M16", "шт", F.MECHANICAL, 100),
    ("Кабель ВВГнг 3х2.5", "CBL-3X25", "м", F.ELECTRICAL, 200),
    ("Автоматический выключатель 25А", "QF-25", "шт", F.ELECTRICAL, 6),
    ("Контактор КМИ-23210", "KM-23210", "шт", F.ELECTRICAL, 4),
    ("Масло гидравлическое ВМГЗ", "OIL-VMGZ", "л", F.HYDRAULIC, 200),
    ("Рукав высокого давления 2SN-16", "RVD-16", "шт", F.HYDRAULIC, 6),
    ("Смазка Литол-24", "LUB-L24", "кг", F.LUBRICATION, 10),
    ("Датчик давления ПД-100", "SNS-PD100", "шт", F.INSTRUMENTATION, 2),
]

# login, password, pin, fio, role, specialty, grade, brigade, shift
USERS = [
    ("admin", "Admin#2026", None, "Администратор Системы", Role.ADMIN, None, None, None, None),
    ("master1", "Master#2026", "1111", "Ахметов Ерлан Серикович", Role.MASTER, "Мастер смены", None, None, Shift.DAY),
    ("boss", "Boss#2026", None, "Ковалёв Андрей Петрович", Role.MANAGER, "Начальник участка", None, None, None),
    ("1001", "Worker#2026", "2580", "Иванов Сергей Николаевич", Role.EXECUTOR, "Слесарь-ремонтник", 5, "Бригада №1 (мех.)", Shift.DAY),
    ("1002", "Worker#2026", "2580", "Жумабаев Нурлан Канатович", Role.EXECUTOR, "Слесарь-ремонтник", 4, "Бригада №1 (мех.)", Shift.DAY),
    ("1003", "Worker#2026", "2580", "Петренко Олег Викторович", Role.EXECUTOR, "Электромонтёр", 5, "Бригада №2 (эл.)", Shift.DAY),
    ("1004", "Worker#2026", "2580", "Садыков Арман Болатович", Role.EXECUTOR, "Электрогазосварщик", 4, "Бригада №1 (мех.)", Shift.NIGHT),
]


BRIGADES = ["Бригада №1 (мех.)", "Бригада №2 (эл.)"]


async def seed_references(db: AsyncSession) -> bool:
    """Примеры справочников (участки, оборудование, бригады, шифры, материалы).
    Ничего не делает, если участки уже заведены. Коммит — на вызывающей стороне."""
    if await db.scalar(select(Workshop.id).limit(1)):
        return False
    for ws_name, items in WORKSHOPS.items():
        ws = Workshop(name=ws_name)
        db.add(ws)
        await db.flush()
        for name, inv, crit in items:
            db.add(Equipment(name=name, inventory_number=inv, workshop_id=ws.id, criticality=crit))
    db.add_all(Brigade(name=name) for name in BRIGADES)
    db.add_all(FaultCode(code=c, name=n, category=cat) for c, n, cat in FAULT_CODES)
    db.add_all(Material(name=n, sku=sku, unit=u, category=cat, max_per_order=mx) for n, sku, u, cat, mx in MATERIALS)
    await db.flush()
    return True


async def seed() -> None:
    """Полный демо-стенд: справочники + демо-пользователи с известными паролями."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.login == "admin")):
            print("Seed: данные уже есть, пропускаю")
            return

        await seed_references(db)
        brigades = {b.name: b for b in await db.scalars(select(Brigade))}
        for login, pwd, pin, fio, role, spec, grade, brigade, shift in USERS:
            db.add(
                User(
                    login=login,
                    password_hash=hash_secret(pwd),
                    pin_hash=hash_secret(pin) if pin else None,
                    fio=fio,
                    role=role,
                    specialty=spec,
                    grade=grade,
                    brigade_id=brigades[brigade].id if brigade in brigades else None,
                    shift=shift,
                    on_shift=shift == Shift.DAY,
                )
            )
        await db.commit()
        print("Seed: готово. Логины: admin / master1 / boss / 1001–1004 (пароли — в app/seed.py)")


if __name__ == "__main__":
    asyncio.run(seed())
