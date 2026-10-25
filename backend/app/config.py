from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    # A public demo anyone may open: the sign-in page offers one click into the seeded portfolio instead of
    # asking for credentials. Only ever turn this on for an instance that holds no real data.
    demo_mode: bool = False
    # Shown on the demo's sign-in page and banner, if the code is public.
    demo_source_url: str | None = None
    default_user_email: str = "owner@jacklyn.local"
    default_user_name: str = "Jacklyn Owner"
    default_base_currency: str = "CHF"

    # Live market data (yfinance) and the daily IBKR auto-sync. Disable for offline use or tests.
    live_market_data: bool = True
    market_data_ttl_seconds: int = 900
    # Optional free key from https://eulerpool.com/developers/register: real country mixes and full holdings
    # for funds on the Health page. Without it, fund countries are estimated from the index a fund tracks.
    eulerpool_token: str | None = None

    max_upload_mb: int = 20
    # A database snapshot a day in data_dir/backups (SQLite only), keeping the last 14; and the largest
    # backup the restore page accepts.
    auto_backups: bool = True
    max_restore_mb: int = 2048

    # Where generated secrets (secret.key, setup-token.txt) and caches live. A Docker volume in production.
    data_dir: Path = BACKEND_DIR / "data"
    # Encrypts TOTP secrets and broker API tokens at rest. Generated into data_dir if unset.
    secret_key: str | None = None
    # One-time token for the first-run admin setup. Generated and logged if unset.
    setup_token: str | None = None

    # Sessions & login protection
    session_days: int = 30
    # "auto": Secure cookies whenever the request arrived over HTTPS (e.g. through Cloudflare).
    cookie_secure: Literal["auto", "true", "false"] = "auto"
    login_ip_max_failures: int = 20  # per IP per 15 minutes
    lockout_threshold: int = 5  # consecutive failures before an account is locked
    lockout_minutes: int = 15
    invite_days: int = 7

    @field_validator("default_base_currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
