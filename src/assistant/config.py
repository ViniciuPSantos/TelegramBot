from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Config da aplicacao, lida de env e variaveis de ambiente"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: SecretStr
    allowed_chat_id: int

    # Infra
    database_url: str = "sqlite+aiossqlite:///./data/assistant.db"
    timezone: str = "America/Sao_Paulo"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "text"
    # Lembretes
    reminder_default_hour: int = Field(default=9, ge=0, le=23)
    reminder_poll_seconds: int = Field(default=30, ge=5)

    @field_validator("timezone")
    @classmethod
    def _validate_timzone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"timezone invalido: {value}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
