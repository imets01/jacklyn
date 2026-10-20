"""Dividend income: one fund held in two accounts whose brokers book the same quarterly dividend on different days
and record withholding differently, plus interest, all checked against hand-worked totals."""

import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ImportSource, PriceSource
from app.enums import TransactionType as T
from app.models import Account, Asset, AssetPrice, User
from app.schemas.standard import StandardTransaction
from app.services.income import income_report
from app.services.ingestion import ingest_transactions
from app.services.portfolio import PortfolioEngine

D = dt.date
QUARTERS = [D(2025, 3, 15), D(2025, 6, 15), D(2025, 9, 15), D(2025, 12, 15), D(2026, 3, 15)]


def _tx(**fields: object) -> StandardTransaction:
    return StandardTransaction.model_validate({"currency": "USD", **fields})


def _setup(db: Session, user: User, account: Account) -> None:
    other = Account(user_id=user.id, name="Second broker", broker="Other", currency="USD")
    db.add(other)
    db.commit()
    # Account one: 10 shares; withholding in the dividend row's tax column (like Lightyear). Plus interest.
    first = [_tx(date=D(2025, 1, 2), type=T.BUY, symbol="ZZINC", quantity=10, unit_price=100)]
    first += [_tx(date=day, type=T.DIVIDEND, symbol="ZZINC", amount="5", tax="0.75") for day in QUARTERS]
    first.append(_tx(date=D(2026, 1, 31), type=T.INTEREST, amount="2"))
    # Account two: 20 shares; paid a day later, withholding as its own tax row (like IBKR).
    second = [_tx(date=D(2025, 1, 2), type=T.BUY, symbol="ZZINC", quantity=20, unit_price=100)]
    for day in QUARTERS:
        later = day + dt.timedelta(days=1)
        second += [
            _tx(date=later, type=T.DIVIDEND, symbol="ZZINC", amount="10"),
            _tx(date=later, type=T.TAX, symbol="ZZINC", amount="1.5"),
        ]
    for target, rows in ((account, first), (other, second)):
        ingest_transactions(db, user_id=user.id, account_id=target.id, transactions=rows, source=ImportSource.FILE)
    asset = db.scalars(select(Asset).where(Asset.symbol == "ZZINC")).one()
    db.add(AssetPrice(asset_id=asset.id, price_date=D(2026, 4, 1), close=Decimal(100), source=PriceSource.YFINANCE))
    db.commit()


def test_income_across_two_brokers(db: Session, user: User, account: Account) -> None:
    _setup(db, user, account)
    report = income_report(PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=D(2026, 4, 1)))

    # Last 12 months: four quarters of 4.25 (account one) and 8.50 (account two), plus 2 of interest.
    totals = report.totals
    assert totals.trailing_12m == Decimal("53.00")
    assert totals.this_year == Decimal("14.75")  # March's two payments and January's interest
    assert totals.withheld_12m == Decimal("9.00")
    assert totals.all_time == Decimal("65.75")
    assert totals.expected_12m == Decimal("51.00")  # 1.70 a share a year x 30 shares
    assert totals.portfolio_yield == Decimal("0.0177")  # 53 / 3,000

    [fund] = report.holdings
    assert (fund.symbol, fund.held, fund.cadence, fund.payments_12m) == ("ZZINC", True, "quarterly", 4)
    assert fund.trailing_12m == Decimal("51.00")
    assert fund.yield_pct == Decimal("0.0170")
    assert fund.last_paid == D(2026, 3, 16)
    # The next one: about a quarter after account one's last payment, 0.425 a share on all 30 shares.
    assert fund.next_expected == D(2026, 6, 14)
    assert fund.next_estimate == Decimal("12.75")
    assert [(p.symbol, p.expected_on) for p in report.upcoming] == [("ZZINC", D(2026, 6, 14))]

    assert len(report.months) == 24
    assert report.months[-1].month == D(2026, 4, 1)
    march = next(m for m in report.months if m.month == D(2026, 3, 1))
    assert (march.dividends, march.withheld, march.interest) == (Decimal("12.75"), Decimal("2.25"), Decimal(0))
    january = next(m for m in report.months if m.month == D(2026, 1, 1))
    assert january.interest == Decimal("2.00")


def test_sold_holdings_keep_their_history_without_expectations(db: Session, user: User, account: Account) -> None:
    rows = [
        _tx(date=D(2025, 1, 2), type=T.BUY, symbol="ZZGONE", quantity=5, unit_price=10),
        _tx(date=D(2025, 6, 1), type=T.DIVIDEND, symbol="ZZGONE", amount="3"),
        _tx(date=D(2025, 9, 1), type=T.DIVIDEND, symbol="ZZGONE", amount="3"),
        _tx(date=D(2025, 10, 1), type=T.SELL, symbol="ZZGONE", quantity=5, unit_price=12),
    ]
    ingest_transactions(db, user_id=user.id, account_id=account.id, transactions=rows, source=ImportSource.FILE)
    [gone] = income_report(PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=D(2026, 4, 1))).holdings
    assert (gone.held, gone.trailing_12m, gone.expected_12m) == (False, Decimal("6.00"), Decimal("0.00"))
    assert (gone.next_expected, gone.yield_pct) == (None, None)


def test_income_endpoint(client: TestClient) -> None:
    response = client.get("/api/portfolio/income", params={"base": "EUR"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base_currency"] == "EUR"
    assert len(body["months"]) == 24
