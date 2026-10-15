from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, str_enum
from app.models.enums import AssetClass
from app.models.types import SafeDecimal


class Asset(UserOwnedMixin, TimestampMixin, Base):
    """An instrument as known to one user (same ticker in two currencies = two assets)."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("id", "user_id"),
        UniqueConstraint("user_id", "symbol", "currency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    asset_class: Mapped[AssetClass] = mapped_column(str_enum(AssetClass), default=AssetClass.EQUITY)
    currency: Mapped[str] = mapped_column(String(3))
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(SafeDecimal(), nullable=True)
    last_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
