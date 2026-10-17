import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import utcnow


class InvestorProfile(Base):
    """What the Health page needs to know about the investor. One row per user, all fields optional."""

    __tablename__ = "investor_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_year: Mapped[int | None]
    horizon_years: Mapped[int | None]  # years until the money is needed; negative = already drawing on it
    risk_tolerance: Mapped[str] = mapped_column(String(16), default="balanced")
    goal: Mapped[str | None] = mapped_column(String(40))
    home_country: Mapped[str] = mapped_column(String(64), default="Switzerland")
    emergency_fund: Mapped[Decimal | None]  # in the user's base currency
    monthly_contribution: Mapped[Decimal | None]
    min_order: Mapped[Decimal] = mapped_column(default=Decimal(0))
    fractional_shares: Mapped[bool] = mapped_column(default=True)
    # {"equity": "0.7", "bonds": "0.2", "commodities": "0.1"}; replaces the suggested targets when set
    target_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    updated_at: Mapped[dt.datetime] = mapped_column(default=utcnow, onupdate=utcnow)
