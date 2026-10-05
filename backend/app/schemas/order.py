from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AIVerdict,
    OrderAction,
    OrderStatus,
    OrderType,
    PhotoType,
    Priority,
)
from app.schemas.reference import EquipmentOut, FaultCodeOut, WorkshopOut
from app.schemas.user import UserShort


class OrderCreate(BaseModel):
    type: OrderType
    description: str = Field(min_length=5, max_length=4000)
    workshop_id: int
    equipment_id: int | None = None
    executor_id: int | None = None
    brigade_id: int | None = None
    priority: Priority = Priority.MEDIUM
    deadline: datetime
    equipment_stopped: bool = False

    @model_validator(mode="after")
    def _assignee(self):
        if self.executor_id is None and self.brigade_id is None:
            raise ValueError("Укажите исполнителя или бригаду")
        if self.deadline.tzinfo is None:
            raise ValueError("deadline должен содержать часовой пояс (ISO 8601 с offset)")
        return self


class OrderUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=5, max_length=4000)
    equipment_id: int | None = None
    priority: Priority | None = None
    deadline: datetime | None = None
    equipment_stopped: bool | None = None


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ReassignIn(BaseModel):
    executor_id: int | None = None
    brigade_id: int | None = None
    deadline: datetime | None = None
    reason: str | None = None


class MaterialUse(BaseModel):
    material_id: int | None = None
    material_name: str | None = Field(default=None, max_length=200)
    quantity: float = Field(gt=0, le=100000)
    unit: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _name(self):
        if self.material_id is None and not self.material_name:
            raise ValueError("Укажите material_id из справочника или material_name")
        return self


class CompleteIn(BaseModel):
    """Форма закрытия наряда исполнителем."""

    work_report: str = Field(min_length=1, max_length=8000)
    fault_code_id: int
    materials: list[MaterialUse] = Field(default_factory=list, max_length=50)


class ApproveIn(BaseModel):
    master_score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: OrderAction
    from_status: OrderStatus | None
    to_status: OrderStatus | None
    reason: str | None
    timestamp: datetime
    user: UserShort | None


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: PhotoType
    url: str
    meta: dict | None
    created_at: datetime


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int | None
    material_name: str
    quantity: float
    unit: str


class AIReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    verdict: AIVerdict
    score: float
    photo_score: float | None
    explanation: str
    checks: list | None
    source: str
    created_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str | None
    type: OrderType
    description: str
    workshop: WorkshopOut
    equipment: EquipmentOut | None
    executor: UserShort | None
    brigade_id: int | None
    master: UserShort
    priority: Priority
    deadline: datetime
    status: OrderStatus
    is_overdue: bool = False
    equipment_stopped: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    master_score: int | None
    allowed_actions: list[str] = Field(default_factory=list)


class OrderDetail(OrderOut):
    work_report: str | None
    fault_code: FaultCodeOut | None
    events: list[EventOut]
    photos: list[PhotoOut]
    materials: list[MaterialOut]
    ai_report: AIReportOut | None = None


class BoardColumn(BaseModel):
    key: str
    title: str
    orders: list[OrderOut]


class ShiftCounters(BaseModel):
    issued: int
    completed: int
    overdue: int
    equipment_down: int
    in_progress: int
