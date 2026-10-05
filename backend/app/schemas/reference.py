from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Criticality, FaultCategory


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int


class WorkshopIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkshopOut(_Out, WorkshopIn):
    pass


class EquipmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    inventory_number: str = Field(min_length=1, max_length=50)
    workshop_id: int
    criticality: Criticality = Criticality.B


class EquipmentOut(_Out, EquipmentIn):
    pass


class BrigadeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    workshop_id: int | None = None


class BrigadeOut(_Out, BrigadeIn):
    pass


class FaultCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    category: FaultCategory


class FaultCodeOut(_Out, FaultCodeIn):
    pass


class MaterialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=50)
    unit: str = Field(default="шт", max_length=20)
    category: FaultCategory = FaultCategory.OTHER
    max_per_order: float | None = Field(default=None, gt=0)


class MaterialOut(_Out, MaterialIn):
    pass
