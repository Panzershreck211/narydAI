from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from app.core.deps import DB, CurrentUser
from app.core.i18n import Localized
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int | None
    kind: str
    title: Localized
    body: Localized
    is_emergency: bool
    is_read: bool
    created_at: datetime


@router.get("", response_model=list[NotificationOut])
async def my_notifications(db: DB, user: CurrentUser, unread_only: bool = False, limit: int = Query(default=50, ge=1, le=200)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return (await db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit))).all()


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: int, db: DB, user: CurrentUser):
    n = await db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    n.is_read = True
    await db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(db: DB, user: CurrentUser):
    await db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    await db.commit()
