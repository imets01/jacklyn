from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UserOwnedMixin, str_enum
from app.models.enums import TransactionType
from app.models.types import SafeDecimal

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.asset import Asset


class Transaction(UserOwnedMixin, TimestampMixin, Base):
    """One cash and/or position movement in an account.

    ``amount`` is the signed net cash impact in ``currency`` (fees included):
    a buy is negative, a dividend positive. ``fee`` is kept for reporting only.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        # Composite FKs: the referenced account/asset must belong to the same user.
        ForeignKeyConstraint(
            ["account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="CASCADE",
            name="fk_transactions_account_user",
        ),
        ForeignKeyConstraint(
            ["asset_id", "user_id"],
            ["assets.id", "assets.user_id"],
            name="fk_transactions_asset_user",
        ),
        UniqueConstraint("account_id", "fingerprint"),
        Index("ix_transactions_user_date", "user_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    import_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_logs.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[TransactionType] = mapped_column(str_enum(TransactionType))
    trade_date: Mapped[date] = mapped_column(Date)
    settle_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(SafeDecimal(), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(SafeDecimal(), nullable=True)
    amount: Mapped[Decimal] = mapped_column(SafeDecimal())
    fee: Mapped[Decimal] = mapped_column(SafeDecimal(), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Deterministic hash of the economic content; makes re-imports idempotent.
    fingerprint: Mapped[str] = mapped_column(String(64))

    account: Mapped["Account"] = relationship(
        back_populates="transactions", foreign_keys=[account_id], overlaps="transactions"
    )
    asset: Mapped["Asset | None"] = relationship(foreign_keys=[asset_id], overlaps="account")
