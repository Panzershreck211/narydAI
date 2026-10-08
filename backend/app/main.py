import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import (
    assistant,
    auth,
    connection,
    dashboard,
    notifications,
    orders,
    references,
    setup,
    users,
    ws,
)
from app.core.config import settings
from app.core.i18n import FRAMEWORK_RU, pick_lang, tr, use_lang, validation_message
from app.core.security import ensure_jwt_secret
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.ai import deadline_monitor

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await ensure_jwt_secret(db)

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


class LangMiddleware:
    """Язык ответа: заголовок Accept-Language (клиенты шлют выбранный в интерфейсе), для WebSocket — ?lang=."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        header = dict(scope.get("headers") or []).get(b"accept-language", b"").decode("latin-1")
        query = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("lang", [None])[0]
        with use_lang(pick_lang(query or header)):
            await self.app(scope, receive, send)


app.add_middleware(LangMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, str):
        detail = tr(FRAMEWORK_RU.get(detail, detail))
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # Pydantic отвечает по-английски («Field required») — отдаём «Пароль: обязательное поле»
    errors = [{"loc": e.get("loc"), "type": e.get("type"), "msg": validation_message(e)} for e in exc.errors()]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


for r in (
    setup.router,
    auth.router,
    users.router,
    references.router,
    orders.router,
    dashboard.router,
    notifications.router,
    assistant.router,
    connection.router,
):
    app.include_router(r, prefix=settings.api_prefix)
app.include_router(ws.router)

# MVP: фото отдаются статикой. В проде — S3/MinIO с подписанными ссылками.
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}
