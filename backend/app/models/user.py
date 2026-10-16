import datetime as dt

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.db.types import EncryptedText
from app.models._common import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)  # stored lower-case
    display_name: Mapped[str] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(3), default="CHF")
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    # None until the account is claimed (first-run setup) or registered through an invite.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[dt.datetime | None]
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[dt.datetime | None]

    totp_secret: Mapped[str | None] = mapped_column(EncryptedText())
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    totp_last_step: Mapped[int | None]  # replay protection: a code's time step is accepted once
