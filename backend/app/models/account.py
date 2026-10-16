import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.enums import AccountType
from app.models._common import enum_column, utcnow


class Account(Base):
    """A single account at any institution. `broker` is free text, so any bank or broker fits."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        CheckConstraint(
            "(account_type = 'tbsz' AND tbsz_year IS NOT NULL) OR (account_type != 'tbsz' AND tbsz_year IS NULL)",
            name="tbsz_year_matches_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    broker: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[AccountType] = mapped_column(enum_column(AccountType), default=AccountType.STANDARD)
    tbsz_year: Mapped[int | None]
    currency: Mapped[str] = mapped_column(String(3))
    external_account_id: Mapped[str | None] = mapped_column(String(64))
    # When False (e.g. a trades-only export), cash balances are ignored and buys count as contributions.
    track_cash: Mapped[bool] = mapped_column(default=True)
    is_archived: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
