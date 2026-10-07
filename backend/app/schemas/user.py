from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.i18n import field_label
from app.models.enums import Availability, Role, Shift


class UserBase(BaseModel):
    fio: str = Field(min_length=3, max_length=200)
    role: Role
    specialty: str | None = Field(default=None, max_length=100)
    grade: int | None = Field(default=None, ge=1, le=6)
    brigade_id: int | None = None
    shift: Shift | None = None


class UserCreate(UserBase):
    login: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=128)
    pin: str | None = Field(default=None, pattern=r"^\d{4,6}$")


class UserUpdate(BaseModel):
    fio: str | None = Field(default=None, min_length=3, max_length=200)
    role: Role | None = None
    specialty: str | None = None
    grade: int | None = Field(default=None, ge=1, le=6)
    brigade_id: int | None = None
    shift: Shift | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _no_null_for_required(self):
        # PATCH: поле можно не передавать, но «очистить» обязательное поле нельзя
        nulls = sorted(k for k in self.model_fields_set - {"specialty", "grade", "brigade_id", "shift"} if getattr(self, k) is None)
        if nulls:
            raise ValueError(f"Поля не могут быть пустыми: {', '.join(field_label(k, 'ru') for k in nulls)}")
        return self


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    pin: str | None = Field(default=None, pattern=r"^\d{4,6}$")


class ShiftUpdate(BaseModel):
    on_shift: bool


class DeviceTokenIn(BaseModel):
    fcm_token: str = Field(max_length=255)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    fio: str
    role: Role
    specialty: str | None
    grade: int | None
    brigade_id: int | None
    shift: Shift | None
    is_active: bool
    on_shift: bool
    has_pin: bool = False
    created_at: datetime

    @classmethod
    def from_user(cls, user) -> "UserOut":
        out = cls.model_validate(user)
        out.has_pin = user.pin_hash is not None
        return out


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fio: str
    specialty: str | None = None
    grade: int | None = None


class ExecutorAvailability(UserShort):
    brigade_id: int | None
    availability: Availability
    active_orders: int
    queued_orders: int
