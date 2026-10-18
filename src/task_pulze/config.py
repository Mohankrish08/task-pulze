from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TASK_PULZE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    public_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:8000"),
        description="Public base URL clients use to reach this server (https in production).",
    )
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    secret_key: SecretStr = Field(description="Fernet key used to encrypt stored Todoist tokens.")
    database_url: SecretStr | None = Field(
        default=None,
        description="Postgres URL (e.g. Supabase). When unset, SQLite at db_path is used.",
    )
    db_path: Path = Path("task_pulze.db")
    db_pool_size: int = Field(default=10, ge=1, le=100)
    log_level: LogLevel = "INFO"
    access_token_ttl: int = Field(default=3600, ge=60)
    refresh_token_ttl: int = Field(default=30 * 24 * 3600, ge=3600)

    @property
    def base_url(self) -> str:
        return str(self.public_url).rstrip("/")

    @property
    def public_host(self) -> str:
        return urlsplit(self.base_url).netloc


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
