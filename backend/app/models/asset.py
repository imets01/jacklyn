import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.db.types import DecimalType
from app.enums import AssetClass, PriceSource
from app.models._common import enum_column, utcnow


class Asset(Base):
    """A tradable instrument. Shared reference data (not user-owned): a quote is the same for everyone.

    Identity is (symbol, currency) because one ISIN can list in several currencies
    (e.g. IE00BK5BQT80 trades as VWCE in EUR and VWRA in USD) at different prices.
    """

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("symbol", "currency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    asset_class: Mapped[AssetClass] = mapped_column(enum_column(AssetClass), default=AssetClass.STOCK)
    currency: Mapped[str] = mapped_column(String(3))
    exchange: Mapped[str | None] = mapped_column(String(32))
    yf_ticker: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class AssetPrice(Base):
    """Daily close cache (synthetic seed, yfinance or imported). Latest row doubles as the live quote."""

    __tablename__ = "asset_prices"
    __table_args__ = (UniqueConstraint("asset_id", "price_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    price_date: Mapped[dt.date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(DecimalType(28, 10))
    source: Mapped[PriceSource] = mapped_column(enum_column(PriceSource))
    fetched_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class FxRate(Base):
    """Daily FX quote stored as 1 `base` = `rate` `quote`. Base is USD; crosses are triangulated."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base", "quote", "rate_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[dt.date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(DecimalType(28, 12))
    source: Mapped[PriceSource] = mapped_column(enum_column(PriceSource))
    fetched_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
