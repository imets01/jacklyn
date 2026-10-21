import datetime as dt
import threading
from decimal import Decimal
from typing import Any, ClassVar

import pandas as pd
import pytest
import yfinance
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.enums import ImportSource, PriceSource, TransactionType
from app.models import Account, Asset, AssetPrice, AssetSplit, FxRate, User
from app.schemas.standard import StandardTransaction
from app.services import market_data
from app.services.ingestion import ingest_transactions
from app.services.portfolio import PortfolioEngine


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


def _refresh_assets(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    quotes: dict[str, float],
    splits: dict[str, dict[dt.date, float]] | None = None,
) -> list[tuple[list[str], dt.date]]:
    """Run the price step against a fake Yahoo that only knows `quotes` (and `splits`); returns its requests."""
    requests: list[tuple[list[str], dt.date]] = []

    def download(tickers: list[str], start: dt.date, **_: Any) -> dict[str, market_data.History]:
        requests.append((tickers, start))
        return {
            t: market_data.History(closes={dt.date(2025, 3, 4): quotes[t]}, splits=(splits or {}).get(t, {}))
            for t in tickers
            if t in quotes
        }

    monkeypatch.setattr(market_data, "_download_history", download)
    service = market_data.MarketDataService(sessionmaker(), get_settings())
    service._refresh_assets(db, market_data.RefreshReport())
    db.commit()
    return requests


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


def test_trade_priced_assets_have_no_day_move(db: Session, user: User, account: Account) -> None:
    """Without market data an asset is valued at its trades; two trades months apart are not a daily change."""
    buys = [
        StandardTransaction(
            date=day,
            type=TransactionType.BUY,
            isin="AT0000A09GU1",
            quantity=Decimal(1),
            unit_price=price,
            currency="EUR",
        )
        for day, price in ((dt.date(2024, 4, 2), Decimal(38)), (dt.date(2026, 9, 30), Decimal("100.86")))
    ]
    ingest_transactions(db, user_id=user.id, account_id=account.id, transactions=buys, source=ImportSource.FILE)
    engine = PortfolioEngine(db, user_id=user.id, base_currency="EUR")
    asset_id = db.scalars(select(Asset.id).where(Asset.isin == "AT0000A09GU1")).one()
    detail = engine.holding_detail(asset_id)
    assert detail is not None
    assert detail.price == Decimal("100.86")
    assert (detail.previous_close, detail.price_change_pct, detail.day_change) == (None, None, Decimal(0))
    assert engine.summary().day_change == Decimal(0)


def test_holdings_changed_during_a_refresh_runs_one_more(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"live_market_data": True})
    service = market_data.MarketDataService(sessionmaker(), settings)
    started: list[str] = []

    class FakeThread:
        def __init__(self, target: Any, **_: Any) -> None:
            self.target = target

        def start(self) -> None:
            started.append("refresh")

    monkeypatch.setattr(threading, "Thread", FakeThread)
    for step in ("_refresh_assets", "_refresh_fx", "_refresh_profiles"):
        monkeypatch.setattr(service, step, lambda *_args, **_kwargs: None)

    service._lock.acquire()  # a refresh is running
    service.holdings_changed()  # an import lands meanwhile
    assert started == []
    service._lock.release()

    service.refresh()  # the running refresh finishes ...
    assert started == ["refresh"]  # ... and starts another one for the new holdings


# ------------------------------------------------------------------------------ stock splits


def _trade(day: dt.date, side: TransactionType, quantity: str, price: str) -> StandardTransaction:
    return StandardTransaction(
        date=day, type=side, symbol="NVDA", quantity=Decimal(quantity), unit_price=Decimal(price), currency="USD"
    )


def _nvda(db: Session, user: User, account: Account, *trades: StandardTransaction) -> Asset:
    """NVDA with Yahoo's split-adjusted closes and its 10-for-1 split of 10 June 2024."""
    ingest_transactions(db, user_id=user.id, account_id=account.id, transactions=list(trades), source=ImportSource.FILE)
    asset = db.scalars(select(Asset).where(Asset.symbol == "NVDA")).one()
    for day, close in ((dt.date(2024, 6, 5), "122.44"), (dt.date(2026, 9, 29), "227.10")):
        db.add(AssetPrice(asset_id=asset.id, price_date=day, close=Decimal(close), source=PriceSource.YFINANCE))
    db.add(AssetSplit(asset_id=asset.id, split_date=dt.date(2024, 6, 10), ratio=Decimal(10)))
    db.commit()
    return asset


def test_trades_before_an_unrecorded_split_are_restated(db: Session, user: User, account: Account) -> None:
    """Lightyear's NVDA history: bought before the split at the old price, sold everything after it."""
    buy = _trade(dt.date(2024, 6, 5), TransactionType.BUY, "0.706141240", "1183.80")
    nvda = _nvda(db, user, account, buy)
    engine = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=dt.date(2026, 9, 28))
    position = engine.replay()[account.id].positions[nvda.id]
    assert position.quantity == Decimal("7.06141240")  # today's shares; the cost is unchanged
    cost = Decimal("0.706141240") * Decimal("1183.80")
    assert position.cost_base == cost

    sell = _trade(dt.date(2026, 9, 29), TransactionType.SELL, "7.061412400", "227.1528")
    ingest_transactions(db, user_id=user.id, account_id=account.id, transactions=[sell], source=ImportSource.FILE)
    engine = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=dt.date(2026, 10, 1))
    ledger = engine.replay()[account.id]
    assert ledger.positions[nvda.id].quantity == 0  # not -6.355271
    assert ledger.realized == Decimal("7.061412400") * Decimal("227.1528") - cost


def test_a_trade_the_broker_already_restated_is_left_alone(db: Session, user: User, account: Account) -> None:
    buy = _trade(dt.date(2024, 6, 5), TransactionType.BUY, "7.0614124", "118.38")  # split-adjusted already
    nvda = _nvda(db, user, account, buy)
    engine = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=dt.date(2026, 9, 28))
    assert engine.replay()[account.id].positions[nvda.id].quantity == Decimal("7.0614124")


def test_refresh_fetches_the_whole_split_history_once(
    db: Session, user: User, account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = _hold(db, user, account, "SPLT", "SPLT", "100")
    lookups: list[str] = []

    class SplitHistory:
        def __init__(self, ticker: str) -> None:
            lookups.append(ticker)
            days = pd.to_datetime(["2014-04-03", "2025-06-02"]).tz_localize("America/New_York")
            self.splits = pd.Series([1.998, 2.0], index=days)

    monkeypatch.setattr(yfinance, "Ticker", SplitHistory)
    _refresh_assets(db, monkeypatch, {"SPLT": 50.0})
    stored = [(s.split_date, s.ratio) for s in db.scalars(select(AssetSplit).order_by(AssetSplit.split_date))]
    assert stored == [
        (dt.date(2014, 4, 3), Decimal("1.998")),
        (dt.date(2025, 6, 2), Decimal(2)),
    ]  # all, not just since trades
    assert asset.splits_through == dt.date.today()

    # Afterwards new splits come with the daily download; the full history is not fetched again.
    _refresh_assets(db, monkeypatch, {"SPLT": 50.0}, {"SPLT": {dt.date(2025, 3, 4): 3.0}})
    assert lookups == ["SPLT"]
    assert len(db.scalars(select(AssetSplit)).all()) == 3


def test_history_is_backfilled_when_older_trades_arrive_later(
    db: Session, user: User, account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FX and prices first fetched in 2024; then a 2021 statement is imported: fetch back to it, once."""
    ingest_transactions(
        db,
        user_id=user.id,
        account_id=account.id,
        transactions=[
            StandardTransaction(
                date=dt.date(2021, 3, 11), type=TransactionType.DEPOSIT, amount=Decimal(100), currency="USD"
            )
        ],
        source=ImportSource.FILE,
    )
    for day in (dt.date(2024, 10, 8), dt.date(2026, 10, 20)):
        db.add(FxRate(base="USD", quote="CHF", rate_date=day, rate=Decimal("0.85"), source=PriceSource.YFINANCE))
    db.commit()
    requests: list[tuple[tuple[str, ...], dt.date]] = []

    def download(tickers: list[str], start: dt.date) -> dict[str, dict[dt.date, Any]]:
        requests.append((tuple(tickers), start))
        return {}

    monkeypatch.setattr(market_data, "_download_closes", download)
    service = market_data.MarketDataService(sessionmaker(), get_settings())
    service._refresh_fx(db, market_data.RefreshReport())
    assert any("CHF=X" in tickers and start == dt.date(2021, 3, 4) for tickers, start in requests)

    # Yahoo had nothing older: the next refresh only fetches recent days, not the whole history again.
    requests.clear()
    service._refresh_fx(db, market_data.RefreshReport())
    assert all(start >= dt.date(2026, 10, 1) for tickers, start in requests if "CHF=X" in tickers)
