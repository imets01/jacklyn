import datetime as dt
from decimal import Decimal
from typing import Any, ClassVar

import pytest
import yfinance
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.enums import ImportSource, PriceSource, TransactionType
from app.models import Account, Asset, AssetPrice, User
from app.schemas.standard import StandardTransaction
from app.services import market_data
from app.services.ingestion import ingest_transactions


class FakeTicker:
    LISTINGS: ClassVar[dict[str, dict[str, Any]]] = {
        "QDVE.DE": {"currency": "EUR", "lastPrice": 46.51},
        "SAME.DE": {"currency": "EUR", "lastPrice": 900.0},  # same symbol, different security
        "SAME.AS": {"currency": "EUR", "lastPrice": 31.0},
        "USDONLY": {"currency": "USD", "lastPrice": 10.0},
        "BRK-B": {"currency": "USD", "lastPrice": 480.0},
        "IUIT.L": {"currency": "USD", "lastPrice": 40.0},  # London's USD line
        "TWICE": {"currency": "USD", "lastPrice": 40.0},
        "TWICE.L": {"currency": "USD", "lastPrice": 41.0},
        "OLD.L": {"currency": "USD", "lastPrice": 10.0},
    }

    def __init__(self, ticker: str) -> None:
        if ticker not in self.LISTINGS:
            raise KeyError(ticker)
        self.fast_info = self.LISTINGS[ticker]


@pytest.fixture(autouse=True)
def fake_yahoo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)


def test_find_listing_matches_currency_and_plausible_price() -> None:
    assert market_data.find_listing("QDVE", "EUR", Decimal("32.77")) == "QDVE.DE"


def test_find_listing_skips_implausible_prices() -> None:
    assert market_data.find_listing("SAME", "EUR", Decimal("30")) == "SAME.AS"


def test_find_listing_requires_matching_currency() -> None:
    assert market_data.find_listing("USDONLY", "EUR", Decimal("10")) is None
    assert market_data.find_listing("UNKNOWN", "EUR", Decimal("10")) is None


def test_find_listing_maps_us_share_classes() -> None:
    assert market_data.find_listing("BRK.B", "USD", Decimal("481.67")) == "BRK-B"


def test_find_listing_tries_london_for_usd() -> None:
    assert market_data.find_listing("IUIT", "USD", Decimal("33.10")) == "IUIT.L"


def test_find_listing_skips_the_excluded_ticker() -> None:
    assert market_data.find_listing("TWICE", "USD", Decimal("40")) == "TWICE"
    assert market_data.find_listing("TWICE", "USD", Decimal("40"), exclude="TWICE") == "TWICE.L"


# ------------------------------------------------------------------------------ refresh


def _hold(db: Session, user: User, account: Account, symbol: str, ticker: str, price: str) -> Asset:
    """A held USD asset whose stored Yahoo ticker is `ticker` (as older imports guessed it)."""
    buy = StandardTransaction(
        date=dt.date(2025, 3, 3),
        type=TransactionType.BUY,
        symbol=symbol,
        quantity=Decimal(1),
        unit_price=Decimal(price),
        currency="USD",
    )
    ingest_transactions(db, user_id=user.id, account_id=account.id, transactions=[buy], source=ImportSource.FILE)
    asset = db.scalars(select(Asset).where(Asset.symbol == symbol)).one()
    asset.yf_ticker = ticker
    db.commit()
    return asset


def _refresh_assets(db: Session, monkeypatch: pytest.MonkeyPatch, quotes: dict[str, float]) -> None:
    """Run the price step against a fake Yahoo that only knows `quotes`."""

    def download(tickers: list[str], start: dt.date) -> dict[str, dict[dt.date, Any]]:
        return {t: {dt.date(2025, 3, 4): quotes[t]} for t in tickers if t in quotes}

    monkeypatch.setattr(market_data, "_download_closes", download)
    service = market_data.MarketDataService(sessionmaker(), get_settings())
    service._refresh_assets(db, market_data.RefreshReport())
    db.commit()


def test_refresh_finds_a_new_listing_for_tickers_that_never_return_quotes(
    db: Session, user: User, account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _hold(db, user, account, "AAPL", "AAPL", "190")
    brk = _hold(db, user, account, "BRK.B", "BRK.B", "481.67")
    iuit = _hold(db, user, account, "IUIT", "IUIT", "53.04")
    delisted = _hold(db, user, account, "OLD", "OLD", "10")
    db.add(
        AssetPrice(asset_id=delisted.id, price_date=dt.date(2025, 3, 3), close=Decimal(10), source=PriceSource.YFINANCE)
    )
    db.commit()

    _refresh_assets(db, monkeypatch, {"AAPL": 200.0, "BRK-B": 480.0, "IUIT.L": 40.0})

    assert (good.yf_ticker, brk.yf_ticker, iuit.yf_ticker) == ("AAPL", "BRK-B", "IUIT.L")
    assert delisted.yf_ticker == "OLD"  # it used to work: keep its history rather than guess another line
    live = set(db.scalars(select(AssetPrice.asset_id).where(AssetPrice.source == PriceSource.YFINANCE)))
    assert {good.id, brk.id, iuit.id} <= live


def test_refresh_keeps_tickers_when_yahoo_answers_for_nobody(
    db: Session, user: User, account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    brk = _hold(db, user, account, "BRK.B", "BRK.B", "481.67")
    _refresh_assets(db, monkeypatch, {})
    assert brk.yf_ticker == "BRK.B"
