"""Application settings, loaded from environment variables / `.env`.

Every variable uses the ``JACKLYN_`` prefix. ``DATABASE_URL`` is also accepted
unprefixed because most PaaS/Proxmox templates inject it under that name.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_URL = f"sqlite:///{BACKEND_DIR / 'data' / 'jacklyn.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JACKLYN_",
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    database_url: str = Field(
        default=DEFAULT_SQLITE_URL,
        validation_alias=AliasChoices("JACKLYN_DATABASE_URL", "DATABASE_URL"),
    )
    seed_on_startup: bool = True
    default_user_email: str = "demo@jacklyn.local"
    default_base_currency: str = "CHF"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_upload_bytes: int = 10 * 1024 * 1024
    sql_echo: bool = False

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
