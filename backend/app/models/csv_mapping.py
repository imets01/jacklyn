from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, str_enum, utcnow
from app.models.enums import Institution


class CustomCSVMapping(UserOwnedMixin, TimestampMixin, Base):
    """A user-defined column mapping for :class:`GenericCSVParser`.

    ``header_signature`` is a hash of the normalised header row so a file with
    the same layout can be matched to its saved mapping automatically.
    """

    __tablename__ = "custom_csv_mappings"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[Institution] = mapped_column(
        str_enum(Institution), default=Institution.OTHER
    )
    header_signature: Mapped[str] = mapped_column(String(64), index=True)
    # Serialized ``app.parsers.generic_csv.ColumnMapping``.
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
