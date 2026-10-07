from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: пустые строки в .env (FCM_CREDENTIALS_FILE=) считаются «не задано»
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    app_name: str = "НарядAI"
    api_prefix: str = "/api/v1"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://naryad:naryad@localhost:5432/naryad"
    # MVP: таблицы создаются при старте. В проде заменить на Alembic-миграции.
    auto_create_tables: bool = True

    # Пусто или заглушка из .env.example — при первом старте API сгенерирует случайный ключ
    # и сохранит его в БД (app_settings), см. app.core.security.ensure_jwt_secret.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12  # смена
    refresh_token_days: int = 14

    # Защита ПИН-входа от перебора
    pin_max_attempts: int = 5
    pin_lock_minutes: int = 5

    cors_origins: list[str] = ["*"]

    media_dir: Path = Path("media")
    max_photo_mb: int = 10
    max_photos_per_type: int = 5

    # Смены: две по 12 часов, начало дневной — 08:00 местного (Костанай, UTC+5)
    plant_utc_offset_hours: int = 5
    day_shift_start_hour: int = 8

    # ИИ-контроль сроков
    deadline_check_interval_sec: int = 60
    reminder_before_min: int = 30
    ai_monitor_enabled: bool = True

    # ИИ-помощник и смысловая проверка нарядов — Google Gemini (бесплатный ключ из Google AI Studio).
    # Без ключа помощник выключен, а наряды проверяются только правилами.
    gemini_api_key: str | None = None
    llm_model: str = "gemini-3.5-flash"
    # если основная модель перегружена/в лимите — запрос уходит следующей
    llm_fallback_models: list[str] = ["gemini-3.5-flash-lite", "gemini-3.7-flash"]
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Push (FCM). Без файла сервисного аккаунта пуши только логируются.
    fcm_credentials_file: Path | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
