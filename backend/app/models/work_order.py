from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import (
    FINAL_STATUSES,
    AIVerdict,
    OrderAction,
    OrderStatus,
    OrderType,
    PhotoType,
    Priority,
    str_enum,
)
from app.models.reference import Equipment, FaultCode, Workshop
from app.models.user import User


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(30), unique=True)
    type: Mapped[OrderType] = mapped_column(str_enum(OrderType))
    description: Mapped[str] = mapped_column(Text)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), index=True)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), index=True)
    executor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    brigade_id: Mapped[int | None] = mapped_column(ForeignKey("brigades.id"), index=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    priority: Mapped[Priority] = mapped_column(str_enum(Priority), default=Priority.MEDIUM)
    deadline: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), default=OrderStatus.ISSUED, index=True)
    # Оборудование остановлено на время работ — идёт в счётчик «в простое»
    equipment_stopped: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]

    # Форма закрытия
    work_report: Mapped[str | None] = mapped_column(Text)
    fault_code_id: Mapped[int | None] = mapped_column(ForeignKey("fault_codes.id"))
    master_score: Mapped[int | None] = mapped_column(SmallInteger)  # оценка мастера 1–5 при приёмке

    # Флаги ИИ-контроля сроков (чтобы не слать повторно)
    reminder_sent: Mapped[bool] = mapped_column(default=False)
    overdue_notified: Mapped[bool] = mapped_column(default=False)
    risk_notified: Mapped[bool] = mapped_column(default=False)

    workshop: Mapped[Workshop] = relationship(lazy="joined")
    equipment: Mapped[Equipment | None] = relationship(lazy="joined")
    executor: Mapped[User | None] = relationship(foreign_keys=[executor_id], lazy="joined")
    master: Mapped[User] = relationship(foreign_keys=[master_id], lazy="joined")
    fault_code: Mapped[FaultCode | None] = relationship(lazy="joined")

    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order", order_by="OrderEvent.timestamp", cascade="all, delete-orphan"
    )
    photos: Mapped[list["OrderPhoto"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    materials: Mapped[list["OrderMaterial"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    ai_reports: Mapped[list["AIReport"]] = relationship(
        back_populates="order", order_by="AIReport.created_at", cascade="all, delete-orphan"
    )

    def overdue_at(self, now: datetime) -> bool:
        if self.status in FINAL_STATUSES:
            return False
        if self.status == OrderStatus.COMPLETED:
            return self.completed_at is not None and self.completed_at > self.deadline
        return now > self.deadline


class OrderEvent(Base):
    """Журнал жизненного цикла наряда (аудит)."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # None — системное (ИИ)
    action: Mapped[OrderAction] = mapped_column(str_enum(OrderAction))
    from_status: Mapped[OrderStatus | None] = mapped_column(str_enum(OrderStatus))
    to_status: Mapped[OrderStatus | None] = mapped_column(str_enum(OrderStatus))
    reason: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    order: Mapped[WorkOrder] = relationship(back_populates="events")
    user: Mapped[User | None] = relationship(lazy="joined")


class OrderPhoto(Base):
    __tablename__ = "order_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    type: Mapped[PhotoType] = mapped_column(str_enum(PhotoType))
    file_path: Mapped[str] = mapped_column(String(300))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Результат базовой проверки фото: EXIF, резкость, хэш
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[WorkOrder] = relationship(back_populates="photos")


class OrderMaterial(Base):
    __tablename__ = "order_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"))
    material_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3, asdecimal=False))
    unit: Mapped[str] = mapped_column(String(20))

    order: Mapped[WorkOrder] = relationship(back_populates="materials")


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    verdict: Mapped[AIVerdict] = mapped_column(str_enum(AIVerdict))
    score: Mapped[float]                       # 1.0–5.0
    photo_score: Mapped[float | None]          # 1.0–5.0, если есть фото
    explanation: Mapped[str] = mapped_column(Text)
    checks: Mapped[list | None] = mapped_column(JSON)  # детализация по проверкам
    source: Mapped[str] = mapped_column(String(20), default="rules")  # rules | rules+llm
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[WorkOrder] = relationship(back_populates="ai_reports")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))  # new_order | reminder | overdue | risk | status | ai
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    is_emergency: Mapped[bool] = mapped_column(default=False)
    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
