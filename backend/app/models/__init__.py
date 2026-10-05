from app.models.reference import Brigade, Equipment, FaultCode, Material, Workshop
from app.models.setting import AppSetting
from app.models.user import User
from app.models.work_order import (
    AIReport,
    Notification,
    OrderEvent,
    OrderMaterial,
    OrderPhoto,
    WorkOrder,
)

__all__ = [
    "AIReport",
    "AppSetting",
    "Brigade",
    "Equipment",
    "FaultCode",
    "Material",
    "Notification",
    "OrderEvent",
    "OrderMaterial",
    "OrderPhoto",
    "User",
    "WorkOrder",
    "Workshop",
]
