"""Справочники: чтение — всем авторизованным, изменение — администратору."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import DB, AdminUser, CurrentUser
from app.db.base import Base
from app.models import Brigade, Equipment, FaultCode, Material, Workshop
from app.schemas import reference as s

router = APIRouter(prefix="/refs", tags=["references"])


def crud(path: str, model: type[Base], schema_in: type[BaseModel], schema_out: type[BaseModel], order_by, filters=()):
    """Регистрирует list/create/update/delete для справочника."""

    async def _get(db: DB, item_id: int):
        obj = await db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена")
        return obj

    async def _commit(db: DB):
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Дубликат или запись используется в нарядах") from None

    @router.get(f"/{path}", response_model=list[schema_out], name=f"list_{path}")
    async def list_items(db: DB, _: CurrentUser, workshop_id: int | None = None):
        stmt = select(model).order_by(order_by)
        if workshop_id is not None and "workshop_id" in filters:
            stmt = stmt.where(model.workshop_id == workshop_id)
        return (await db.scalars(stmt)).all()

    @router.post(f"/{path}", response_model=schema_out, status_code=201, name=f"create_{path}")
    async def create_item(body: schema_in, db: DB, _: AdminUser):  # type: ignore[valid-type]
        obj = model(**body.model_dump())
        db.add(obj)
        await _commit(db)
        return obj

    @router.put(f"/{path}/{{item_id}}", response_model=schema_out, name=f"update_{path}")
    async def update_item(item_id: int, body: schema_in, db: DB, _: AdminUser):  # type: ignore[valid-type]
        obj = await _get(db, item_id)
        for k, v in body.model_dump().items():
            setattr(obj, k, v)
        await _commit(db)
        return obj

    @router.delete(f"/{path}/{{item_id}}", status_code=204, name=f"delete_{path}")
    async def delete_item(item_id: int, db: DB, _: AdminUser):
        await db.delete(await _get(db, item_id))
        await _commit(db)


crud("workshops", Workshop, s.WorkshopIn, s.WorkshopOut, Workshop.name)
crud("equipment", Equipment, s.EquipmentIn, s.EquipmentOut, Equipment.name, filters=("workshop_id",))
crud("brigades", Brigade, s.BrigadeIn, s.BrigadeOut, Brigade.name, filters=("workshop_id",))
crud("fault-codes", FaultCode, s.FaultCodeIn, s.FaultCodeOut, FaultCode.code)
crud("materials", Material, s.MaterialIn, s.MaterialOut, Material.name)
