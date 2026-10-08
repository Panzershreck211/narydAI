"""Адрес сервера для мобильного приложения (раздел «Настройки» панели).

Сервер работает в Docker и не видит сетевые адреса компьютера, поэтому IP передаёт
скрипт запуска (start.bat / start.sh) через переменную SERVER_LAN_IPS.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import AdminUser

router = APIRouter(tags=["settings"])


class ConnectionOut(BaseModel):
    lan_ips: list[str]  # IP компьютера в локальной сети на момент запуска
    web_port: int  # порт панели: она проксирует /api, /ws и /media для телефона


@router.get("/settings/connection", response_model=ConnectionOut, summary="Адрес сервера для мобильного приложения")
async def get_connection(_: AdminUser):
    ips = [ip.strip() for ip in settings.server_lan_ips.split(",") if ip.strip()]
    return ConnectionOut(lan_ips=list(dict.fromkeys(ips)), web_port=settings.web_port)
