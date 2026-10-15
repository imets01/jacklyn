from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, str_enum
from app.models.enums import ImportStatus


class ImportLog(UserOwnedMixin, TimestampMixin, Base):
    """Audit trail of every file preview/commit."""

    __tablename__ = "import_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="CASCADE",
            name="fk_import_logs_account_user",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_csv_mappings.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    parser_key: Mapped[str] = mapped_column(String(32))
    status: Mapped[ImportStatus] = mapped_column(str_enum(ImportStatus))
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
