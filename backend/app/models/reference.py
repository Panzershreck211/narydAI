"""Справочники, которые ведёт администратор."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Criticality, FaultCategory, str_enum


class Workshop(Base):
    __tablename__ = "workshops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)

    equipment: Mapped[list["Equipment"]] = relationship(back_populates="workshop")


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    inventory_number: Mapped[str] = mapped_column(String(50), unique=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id", ondelete="RESTRICT"), index=True)
    criticality: Mapped[Criticality] = mapped_column(str_enum(Criticality), default=Criticality.B)

    workshop: Mapped[Workshop] = relationship(back_populates="equipment")


class Brigade(Base):
    __tablename__ = "brigades"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey("workshops.id"))


class FaultCode(Base):
    """Шифр неисправности."""

    __tablename__ = "fault_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[FaultCategory] = mapped_column(str_enum(FaultCategory))


class Material(Base):
    """Справочник материалов и запчастей."""

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str | None] = mapped_column(String(50), unique=True)
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    category: Mapped[FaultCategory] = mapped_column(str_enum(FaultCategory), default=FaultCategory.OTHER)
    # Порог «подозрительного» количества на один наряд — используется ИИ-проверкой
    max_per_order: Mapped[float | None]
