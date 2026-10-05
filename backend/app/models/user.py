from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.models.enums import Role, Shift, str_enum


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(50), unique=True)  # табельный номер или логин
    password_hash: Mapped[str] = mapped_column(String(100))
    pin_hash: Mapped[str | None] = mapped_column(String(100))

    fio: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(str_enum(Role), index=True)
    specialty: Mapped[str | None] = mapped_column(String(100))  # слесарь, электрик...
    grade: Mapped[int | None] = mapped_column(SmallInteger)       # разряд 1–6
    brigade_id: Mapped[int | None] = mapped_column(ForeignKey("brigades.id"), index=True)
    shift: Mapped[Shift | None] = mapped_column(str_enum(Shift))

    # «status» из ТЗ разделён на две вещи: учётка активна + человек на смене.
    # Занятость (свободен/в работе/очередь) считается по нарядам — см. services/availability.py
    is_active: Mapped[bool] = mapped_column(default=True)
    on_shift: Mapped[bool] = mapped_column(default=False)

    failed_pin_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None]
    fcm_token: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
