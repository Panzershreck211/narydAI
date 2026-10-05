import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import (
    assistant,
    auth,
    dashboard,
    notifications,
    orders,
    references,
    setup,
    users,
    ws,
)
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.ai import deadline_monitor

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    stop = asyncio.Event()
    monitor = asyncio.create_task(deadline_monitor.run_forever(stop)) if settings.ai_monitor_enabled else None
    yield
    stop.set()
    if monitor:
        await monitor
    await engine.dispose()


settings.media_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Интеллектуальная система выдачи и контроля нарядов (MVP)",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    setup.router,
    auth.router,
    users.router,
    references.router,
    orders.router,
    dashboard.router,
    notifications.router,
    assistant.router,
):
    app.include_router(r, prefix=settings.api_prefix)
app.include_router(ws.router)

# MVP: фото отдаются статикой. В проде — S3/MinIO с подписанными ссылками.
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}
