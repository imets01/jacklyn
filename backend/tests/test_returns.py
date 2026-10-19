"""Money- and time-weighted returns, checked against worked examples."""

import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ImportSource, PriceSource
from app.enums import TransactionType as T
from app.models import Account, Asset, AssetPrice, User
from app.schemas.standard import StandardTransaction
from app.services.ingestion import ingest_transactions
from app.services.portfolio import PortfolioEngine
from app.services.returns import Snapshot, per_year, time_weighted, xirr

D = dt.date
CLOSE = Decimal("0.0001")


def near(value: Decimal | None, expected: str, tolerance: Decimal = CLOSE) -> bool:
    return value is not None and abs(value - Decimal(expected)) <= tolerance


def test_xirr_of_a_plain_year() -> None:
    assert near(xirr([(D(2024, 1, 1), Decimal(-1000)), (D(2024, 12, 31), Decimal(1100))]), "0.1")
    assert xirr([(D(2024, 1, 1), Decimal(-1000)), (D(2024, 6, 1), Decimal(-5))]) is None  # money only went in
    assert near(per_year(Decimal("0.21"), 730), "0.1")


def test_a_big_deposit_before_a_fall() -> None:
    """1,000 grows 20%, then 10,000 more goes in just before a 10% fall: the funds made 8%, your money lost."""
    snapshots = [
        Snapshot(D(2024, 1, 1), Decimal(1000), Decimal(1000)),
        Snapshot(D(2024, 7, 1), Decimal(11200), Decimal(11000)),
        Snapshot(D(2024, 12, 31), Decimal(10080), Decimal(11000)),
    ]
    assert near(time_weighted(snapshots), "0.08")
    flows = [(D(2024, 1, 1), Decimal(-1000)), (D(2024, 7, 1), Decimal(-10000)), (D(2024, 12, 31), Decimal(10080))]
    assert near(xirr(flows), "-0.1481")  # an independent float solver gives -0.148056


def _setup(db: Session, user: User, account: Account) -> Asset:
    """Deposit and buy 10 at 100; the price reaches 120 and 12,000 more goes into 100 shares; it falls to 108."""
    rows = [
        StandardTransaction(date=D(2024, 1, 1), type=T.DEPOSIT, amount=Decimal(1000), currency="CHF"),
        StandardTransaction(
            date=D(2024, 1, 1),
            type=T.BUY,
            symbol="ZZPERF",
            quantity=Decimal(10),
            unit_price=Decimal(100),
            currency="CHF",
        ),
        StandardTransaction(date=D(2024, 7, 1), type=T.DEPOSIT, amount=Decimal(12000), currency="CHF"),
        StandardTransaction(
            date=D(2024, 7, 1),
            type=T.BUY,
            symbol="ZZPERF",
            quantity=Decimal(100),
            unit_price=Decimal(120),
            currency="CHF",
        ),
    ]
    if not account.track_cash:
        rows = [row for row in rows if row.type is not T.DEPOSIT]
    ingest_transactions(db, user_id=user.id, account_id=account.id, transactions=rows, source=ImportSource.FILE)
    asset = db.scalars(select(Asset).where(Asset.symbol == "ZZPERF")).one()
    for day, close in ((D(2024, 1, 1), 100), (D(2024, 7, 1), 120), (D(2024, 12, 31), 108), (D(2025, 3, 31), "118.8")):
        db.add(AssetPrice(asset_id=asset.id, price_date=day, close=Decimal(close), source=PriceSource.YFINANCE))
    db.commit()
    return asset


def test_engine_returns_over_all_time_and_this_year(db: Session, user: User, account: Account) -> None:
    _setup(db, user, account)
    year = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=D(2024, 12, 31)).performance("ALL")
    assert year.total is not None
    assert (year.total.start, year.total.days, year.total.per_year) == (D(2024, 1, 1), 365, True)
    assert near(year.total.time_weighted, "0.08")
    assert near(year.total.money_weighted, "-0.1541")  # float solver: -0.154114
    assert (year.total.net_flows, year.total.end_value, year.total.gain) == (
        Decimal(13000),
        Decimal(11880),
        Decimal(-1120),
    )
    [only] = year.accounts
    assert only.account_id == account.id
    assert only.time_weighted == year.total.time_weighted

    # 2025 so far: no money moved, so both rates are the price change, as a total for three months.
    ytd = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=D(2025, 3, 31)).performance("YTD")
    assert ytd.total is not None
    assert (ytd.total.start, ytd.total.per_year, ytd.total.start_value) == (D(2025, 1, 1), False, Decimal(11880))
    assert near(ytd.total.time_weighted, "0.1")
    assert near(ytd.total.money_weighted, "0.1")


def test_without_cash_tracking_buys_are_the_money_put_in(db: Session, user: User, account: Account) -> None:
    account.track_cash = False
    db.commit()
    _setup(db, user, account)
    total = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=D(2024, 12, 31)).performance("ALL").total
    assert total is not None
    assert near(total.time_weighted, "0.08")
    assert near(total.money_weighted, "-0.1541")


def test_nothing_invested(db: Session, user: User, account: Account) -> None:
    result = PortfolioEngine(db, user_id=user.id, base_currency="CHF").performance("1Y")
    assert (result.total, result.accounts) == (None, [])


def test_performance_endpoint(client: TestClient) -> None:
    response = client.get("/api/portfolio/performance", params={"period": "1Y", "base": "EUR"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base_currency"] == "EUR"
    assert body["total"] is not None
    assert body["accounts"]
    assert client.get("/api/portfolio/performance", params={"period": "2W"}).status_code == 422
