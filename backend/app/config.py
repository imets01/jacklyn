from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables and `.env` files.

    Every variable can be given with a `JACKLYN_` prefix; `DATABASE_URL` is also
    accepted without it so the stack follows the usual Docker convention.
    """

    model_config = SettingsConfigDict(
        env_prefix="JACKLYN_",
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    database_url: str = Field(
        default=f"sqlite:///{(BACKEND_DIR / 'data' / 'jacklyn.db').as_posix()}",
        validation_alias=AliasChoices("JACKLYN_DATABASE_URL", "DATABASE_URL"),
    )
    seed_demo_data: bool = True
    default_user_email: str = "owner@jacklyn.local"
    default_user_name: str = "Jacklyn Owner"
    default_base_currency: str = "CHF"

    # Live market data (yfinance). Disable for offline use or tests.
    live_market_data: bool = True
    market_data_ttl_seconds: int = 900

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_upload_mb: int = 20

    @field_validator("default_base_currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
