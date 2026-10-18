import datetime as dt
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.db.types import EncryptedText
from app.enums import ImportSource, ImportStatus
from app.models._common import enum_column, utcnow


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    source: Mapped[ImportSource] = mapped_column(enum_column(ImportSource))
    status: Mapped[ImportStatus] = mapped_column(enum_column(ImportStatus))
    parser_key: Mapped[str | None] = mapped_column(String(64))
    filename: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    rows_received: Mapped[int] = mapped_column(default=0)
    rows_imported: Mapped[int] = mapped_column(default=0)
    rows_duplicate: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class CustomCSVMapping(Base):
    """A user-saved Universal Column Mapper preset (e.g. "Revolut Trading CSV")."""

    __tablename__ = "custom_csv_mappings"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # SHA-256 of the normalized header row; lets the next upload from the same broker auto-apply.
    header_signature: Mapped[str] = mapped_column(String(64), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class BrokerCredential(Base):
    """API-sync credentials (e.g. IBKR Flex read-only token + query id). The token is encrypted at rest.

    One connection per user and provider: a Flex query may cover several IBKR accounts, and each statement
    is routed to the Jacklyn account whose `external_account_id` matches.
    """

    __tablename__ = "broker_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    token: Mapped[str] = mapped_column(EncryptedText())
    query_id: Mapped[str | None] = mapped_column(String(64))
    auto_sync: Mapped[bool] = mapped_column(default=True)
    last_synced_at: Mapped[dt.datetime | None]  # last run that fetched a statement
    last_attempt_at: Mapped[dt.datetime | None]
    last_status: Mapped[str | None] = mapped_column(String(16))  # ok | partial | failed
    last_message: Mapped[str | None] = mapped_column(Text)
    # Per IBKR account: {"account": "U123", "account_id": 4 | null, "received": .., "imported": .., ...}
    last_result: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
