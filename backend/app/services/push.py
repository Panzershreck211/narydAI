"""Push-уведомления (FCM). Без настроенного сервисного аккаунта — только лог."""

import asyncio
import logging

from app.core.config import settings

log = logging.getLogger(__name__)


class PushSender:
    def __init__(self) -> None:
        self._app = None
        if settings.fcm_credentials_file:
            try:
                import firebase_admin
                from firebase_admin import credentials

                self._app = firebase_admin.initialize_app(
                    credentials.Certificate(str(settings.fcm_credentials_file))
                )
            except Exception:
                log.exception("FCM init failed — push will be logged only")

    async def send(self, token: str | None, title: str, body: str, data: dict[str, str], emergency: bool) -> None:
        if not token or self._app is None:
            log.info("PUSH%s -> %s: %s", " [EMERGENCY]" if emergency else "", title, body)
            return
        from firebase_admin import messaging

        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data=data,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="emergency" if emergency else "orders",
                    color="#D32F2F" if emergency else "#1565C0",
                ),
            ),
        )
        try:
            await asyncio.to_thread(messaging.send, message, app=self._app)
        except Exception:
            log.exception("FCM send failed")


push_sender = PushSender()
