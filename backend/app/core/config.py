from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "НарядAI"
    api_prefix: str = "/api/v1"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://naryad:naryad@localhost:5432/naryad"
    # MVP: таблицы создаются при старте. В проде заменить на Alembic-миграции.
    auto_create_tables: bool = True

    jwt_secret: str = "change-me-in-production-please-32+chars"
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

    # Опциональная LLM-проверка (Claude). Без ключа работают только правила.
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"

    # Push (FCM). Без файла сервисного аккаунта пуши только логируются.
    fcm_credentials_file: Path | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
