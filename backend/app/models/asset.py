import datetime as dt
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, LargeBinary, String, Text, UniqueConstraint
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


class AssetProfile(Base):
    """Descriptive reference data from the market data provider; any field may be missing."""

    __tablename__ = "asset_profiles"

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    quote_type: Mapped[str | None] = mapped_column(String(32))  # Yahoo's ETF / EQUITY / CRYPTOCURRENCY / ...
    long_name: Mapped[str | None] = mapped_column(String(200))
    provider: Mapped[str | None] = mapped_column(String(80))  # fund issuer brand, e.g. "iShares"
    sector: Mapped[str | None] = mapped_column(String(120))
    industry: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(200))
    expense_ratio: Mapped[Decimal | None]  # TER as a fraction: 0.0007 = 0.07% a year
    fund_size: Mapped[Decimal | None]  # total assets, in the listing currency
    # Shared key into asset_logos ("domain:ishares.com", "crypto:btc"), so one issuer's funds share a logo.
    logo_key: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(64))  # company headquarters, for single stocks
    # Fund look-through from Yahoo, as {name: "fraction"} strings so no float ever enters the math.
    sector_weights: Mapped[dict[str, str] | None] = mapped_column(JSON)
    class_weights: Mapped[dict[str, str] | None] = mapped_column(JSON)  # stock / bond / cash / other
    top_holdings: Mapped[dict[str, str] | None] = mapped_column(JSON)  # symbol -> weight, top 10 only
    # From Eulerpool when a key is configured: the fund's real country mix and its full holdings (ISIN -> weight).
    country_weights: Mapped[dict[str, str] | None] = mapped_column(JSON)
    holdings: Mapped[dict[str, str] | None] = mapped_column(JSON)
    fetched_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class AssetLogo(Base):
    """Cached logo image. A row without data records a miss, so the source isn't asked again for a while."""

    __tablename__ = "asset_logos"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    content_type: Mapped[str | None] = mapped_column(String(32))
    data: Mapped[bytes | None] = mapped_column(LargeBinary)
    source: Mapped[str | None] = mapped_column(String(32))
    fetched_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
