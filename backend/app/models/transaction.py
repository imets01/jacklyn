import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.enums import TransactionType
from app.models._common import enum_column, utcnow


class Transaction(Base):
    """A normalized ledger entry. Every importer, sync client and the seeder write these via ingestion.

    Amounts are magnitudes whose direction comes from `type`, except FX_CONVERSION legs,
    where `amount` is signed (+ received, - spent).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "dedup_hash"),
        Index("ix_transactions_user_account_date", "user_id", "account_id", "trade_date"),
        Index("ix_transactions_account_external_id", "account_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    import_log_id: Mapped[int | None] = mapped_column(ForeignKey("import_logs.id", ondelete="SET NULL"))

    trade_date: Mapped[dt.date] = mapped_column(Date)
    type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType))
    quantity: Mapped[Decimal | None]
    unit_price: Mapped[Decimal | None]
    amount: Mapped[Decimal | None]
    fee: Mapped[Decimal] = mapped_column(default=Decimal(0))
    tax: Mapped[Decimal] = mapped_column(default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(Text)

    external_id: Mapped[str | None] = mapped_column(String(128))
    dedup_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
