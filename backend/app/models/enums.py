from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def str_enum(enum_cls: type[StrEnum]) -> SAEnum:
    """Хранит enum как VARCHAR со значениями (а не именами) — проще миграции и отладка."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class Role(StrEnum):
    MASTER = "master"        # мастер смены
    EXECUTOR = "executor"    # исполнитель
    MANAGER = "manager"      # руководитель
    ADMIN = "admin"          # администратор


class Shift(StrEnum):
    DAY = "day"
    NIGHT = "night"


class Availability(StrEnum):
    """Цвет на доске мастера: green / yellow / blue / grey."""

    FREE = "free"            # свободен
    BUSY = "busy"            # в работе
    QUEUED = "queued"        # есть очередь
    OFF_SHIFT = "off_shift"  # не на смене


class OrderType(StrEnum):
    PLANNED = "planned"
    EMERGENCY = "emergency"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OrderStatus(StrEnum):
    ISSUED = "issued"            # выдан
    ACCEPTED = "accepted"        # принят исполнителем
    QUEUED = "queued"            # в очереди у исполнителя
    IN_PROGRESS = "in_progress"  # в работе
    PAUSED = "paused"            # приостановлен
    COMPLETED = "completed"      # исполнен, ждёт приёмки мастером
    CLOSED = "closed"            # принят мастером
    REJECTED = "rejected"        # отклонён исполнителем — нужен новый исполнитель
    CANCELLED = "cancelled"


FINAL_STATUSES = {OrderStatus.CLOSED, OrderStatus.CANCELLED}
# Статусы, в которых наряд ещё «висит» на исполнителе и может просрочиться
OPEN_STATUSES = {
    OrderStatus.ISSUED,
    OrderStatus.ACCEPTED,
    OrderStatus.QUEUED,
    OrderStatus.IN_PROGRESS,
    OrderStatus.PAUSED,
    OrderStatus.REJECTED,
}


class OrderAction(StrEnum):
    CREATE = "create"
    ACCEPT = "accept"
    QUEUE = "queue"
    REJECT = "reject"
    START = "start"
    PAUSE = "pause"
    COMPLETE = "complete"
    APPROVE = "approve"
    RETURN = "return"
    REASSIGN = "reassign"
    CANCEL = "cancel"
    UPDATE = "update"
    PHOTO = "photo"
    REMINDER = "reminder"
    OVERDUE = "overdue"
    RISK = "risk"
    AI_CHECK = "ai_check"


class FaultCategory(StrEnum):
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    HYDRAULIC = "hydraulic"
    PNEUMATIC = "pneumatic"
    INSTRUMENTATION = "instrumentation"  # КИПиА
    LUBRICATION = "lubrication"
    OTHER = "other"


class PhotoType(StrEnum):
    BEFORE = "before"
    AFTER = "after"


class AIVerdict(StrEnum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class Criticality(StrEnum):
    A = "A"  # останов производства
    B = "B"
    C = "C"


# Подписи для текстов, которые видит пользователь (в сообщениях не должно быть кодов вроде «in_progress»)
STATUS_RU = {
    OrderStatus.ISSUED: "Выдан",
    OrderStatus.ACCEPTED: "Принят",
    OrderStatus.QUEUED: "В очереди",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.PAUSED: "Приостановлен",
    OrderStatus.COMPLETED: "Исполнен",
    OrderStatus.CLOSED: "Принят мастером",
    OrderStatus.REJECTED: "Отклонён",
    OrderStatus.CANCELLED: "Отменён",
}
ACTION_RU = {
    OrderAction.ACCEPT: "Принять",
    OrderAction.QUEUE: "В очередь",
    OrderAction.REJECT: "Отклонить",
    OrderAction.START: "Начать",
    OrderAction.PAUSE: "Пауза",
    OrderAction.COMPLETE: "Исполнено",
    OrderAction.APPROVE: "Принять работу",
    OrderAction.RETURN: "Вернуть на доработку",
    OrderAction.REASSIGN: "Переназначить",
    OrderAction.CANCEL: "Отменить",
}
FAULT_CATEGORY_RU = {
    FaultCategory.MECHANICAL: "механика",
    FaultCategory.ELECTRICAL: "электрика",
    FaultCategory.HYDRAULIC: "гидравлика",
    FaultCategory.PNEUMATIC: "пневматика",
    FaultCategory.INSTRUMENTATION: "КИПиА",
    FaultCategory.LUBRICATION: "смазка",
    FaultCategory.OTHER: "прочее",
}
