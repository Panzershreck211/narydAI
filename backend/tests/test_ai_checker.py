"""Юнит-тесты правил ИИ-проверки без БД."""

from datetime import timedelta

from app.db.base import utcnow
from app.models import Equipment, FaultCode, Material, OrderMaterial, WorkOrder
from app.models.enums import AIVerdict, FaultCategory, OrderStatus, OrderType, Priority
from app.services.ai.order_checker import check_order
from app.services.ai.photo_checker import assess_photos


def make_order(report: str, fault: FaultCode, materials=(), minutes: int = 60) -> WorkOrder:
    now = utcnow()
    o = WorkOrder(
        id=1,
        type=OrderType.PLANNED,
        description="Насос ГрАТ: течь масла из-под сальника, падение давления",
        workshop_id=1,
        master_id=1,
        priority=Priority.MEDIUM,
        deadline=now + timedelta(hours=1),
        status=OrderStatus.COMPLETED,
        created_at=now - timedelta(minutes=minutes + 10),
        started_at=now - timedelta(minutes=minutes),
        completed_at=now,
        work_report=report,
    )
    o.equipment = Equipment(name="Насос ГрАТ 1400/40", inventory_number="X", workshop_id=1)
    o.fault_code = fault
    o.materials = list(materials)
    o.photos = []
    return o


HYDRO = FaultCode(code="Г-01", name="Утечка", category=FaultCategory.HYDRAULIC)
ELEC = FaultCode(code="Э-01", name="КЗ", category=FaultCategory.ELECTRICAL)
OIL = Material(id=1, name="Масло ВМГЗ", unit="л", category=FaultCategory.HYDRAULIC, max_per_order=200)
CABLE = Material(id=2, name="Кабель ВВГ", unit="м", category=FaultCategory.ELECTRICAL, max_per_order=200)


def test_good_report_passes():
    o = make_order(
        "Заменено уплотнение сальника насоса, долито гидравлическое масло, течь устранена, давление в норме",
        HYDRO,
        [OrderMaterial(material_id=1, material_name="Масло ВМГЗ", quantity=20, unit="л")],
    )
    res = check_order(o, {1: OIL})
    assert res.verdict == AIVerdict.OK, res.explanation
    assert res.score >= 4


def test_short_and_irrelevant_report_is_rejected():
    o = make_order("Сделано", ELEC, minutes=2)
    res = check_order(o, {})
    assert res.verdict == AIVerdict.REJECTED
    names = {c.name for c in res.checks if c.severity in ("warn", "error")}
    assert {"completeness", "duration"} <= names


def test_illogical_materials_flagged():
    o = make_order(
        "Устранена течь масла насоса, заменено уплотнение сальника, проверено давление в системе",
        HYDRO,
        [
            OrderMaterial(material_id=2, material_name="Кабель ВВГ", quantity=500, unit="м"),
        ],
    )
    res = check_order(o, {2: CABLE})
    names = {c.name for c in res.checks if c.severity == "warn"}
    assert {"material_qty", "material_category"} <= names
    assert res.verdict != AIVerdict.OK


def test_identical_before_after_photos():
    meta = {"has_exif": True, "sharpness": 300, "brightness": 120, "dhash": "f0f0f0f0f0f0f0f0"}
    pc = assess_photos([meta], [dict(meta)], utcnow())
    assert pc.score <= 3
    assert any("идентично" in i for i in pc.issues)
