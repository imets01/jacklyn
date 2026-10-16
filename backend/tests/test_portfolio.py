import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import AccountType, ImportSource, PriceSource, TransactionType
from app.models import Account, Asset, AssetPrice, FxRate, User
from app.schemas.standard import StandardTransaction
from app.services.ingestion import ingest_transactions
from app.services.portfolio import PortfolioEngine
from app.services.tbsz import reduced_rate_from, tax_free_from

D = dt.date
T = TransactionType
AS_OF = D(2025, 3, 2)


@pytest.fixture
def ledger(db: Session, user: User, account: Account) -> Account:
    """USD stock in a CHF-based account with a constant USD/CHF of 0.9 and USD/EUR of 0.8."""
    db.add_all(
        [
            FxRate(base="USD", quote="CHF", rate_date=D(2025, 1, 1), rate=Decimal("0.9"), source=PriceSource.SEED),
            FxRate(base="USD", quote="EUR", rate_date=D(2025, 1, 1), rate=Decimal("0.8"), source=PriceSource.SEED),
        ]
    )
    asset = Asset(symbol="AAPL", currency="USD")
    db.add(asset)
    db.flush()
    for day, close in [(D(2025, 1, 1), "100"), (D(2025, 3, 1), "110"), (D(2025, 3, 2), "120")]:
        db.add(AssetPrice(asset_id=asset.id, price_date=day, close=Decimal(close), source=PriceSource.SEED))
    db.commit()

    def tx(day: dt.date, tx_type: TransactionType, **fields: object) -> StandardTransaction:
        return StandardTransaction.model_validate({"date": day, "type": tx_type, "currency": "USD", **fields})

    ingest_transactions(
        db,
        user_id=user.id,
        account_id=account.id,
        source=ImportSource.MANUAL,
        transactions=[
            tx(D(2025, 1, 1), T.DEPOSIT, amount="2000"),
            tx(D(2025, 1, 2), T.BUY, symbol="AAPL", quantity="10", unit_price="100", fee="1"),
            tx(D(2025, 2, 1), T.SELL, symbol="AAPL", quantity="5", unit_price="110", fee="1"),
            tx(D(2025, 2, 15), T.DIVIDEND, symbol="AAPL", amount="10", tax="1.5"),
            tx(D(2025, 2, 20), T.FEE, amount="2"),
        ],
    )
    return account


def test_summary_math(db: Session, user: User, ledger: Account) -> None:
    summary = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=AS_OF).summary()
    # 5 shares x 120 USD x 0.9 = 540 CHF; cash 1554.5 USD x 0.9 = 1399.05 CHF
    assert summary.holdings_value == Decimal("540.00")
    assert summary.cash == Decimal("1399.05")
    assert summary.net_worth == Decimal("1939.05")
    assert summary.net_contributions == Decimal("1800.00")
    # basis: 1001 USD x 0.9 = 900.90, half sold -> 450.45 left; realized 549 x 0.9 - 450.45
    assert summary.unrealized_pnl == Decimal("89.55")
    assert summary.realized_pnl == Decimal("43.65")
    assert summary.income == Decimal("7.65")
    assert summary.costs == Decimal("1.80")
    assert summary.total_pnl == Decimal("139.05")
    assert summary.total_pnl == summary.net_worth - summary.net_contributions  # constant FX: both views agree
    # 120 vs 110 on the last day: 5 x 10 USD x 0.9
    assert summary.day_change == Decimal("45.00")
    assert summary.warnings == []

    account_summary = summary.accounts[0]
    assert account_summary.holdings_count == 1
    assert account_summary.transaction_count == 5
    assert account_summary.value == summary.net_worth


def test_base_currency_conversion(db: Session, user: User, ledger: Account) -> None:
    eur = PortfolioEngine(db, user_id=user.id, base_currency="EUR", as_of=AS_OF).summary()
    usd = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=AS_OF).summary()
    assert usd.net_worth == Decimal("2154.50")
    assert eur.net_worth == Decimal("1723.60")


def test_allocations_sum_to_one(db: Session, user: User, ledger: Account) -> None:
    allocations = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=AS_OF).summary().allocations
    for slices in (allocations.asset_class, allocations.currency, allocations.broker, allocations.wrapper):
        assert abs(sum((s.weight for s in slices), Decimal(0)) - 1) <= Decimal("0.0002")
    assert {s.key for s in allocations.asset_class} == {"stock", "cash"}


def test_holdings_and_history(db: Session, user: User, ledger: Account) -> None:
    engine = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=AS_OF)
    holdings = engine.holdings()
    assert [(h.symbol, h.quantity, h.value, h.cost_basis) for h in holdings.holdings] == [
        ("AAPL", Decimal(5), Decimal("540.00"), Decimal("450.45"))
    ]
    assert [(c.currency, c.amount) for c in holdings.cash] == [("USD", Decimal("1554.50"))]

    history = engine.history("ALL")
    assert history.points[0].date == D(2025, 1, 1)
    assert history.points[0].value == Decimal("1800.00")
    assert history.points[-1].value == Decimal("1939.05")
    assert history.change == Decimal("139.05")


def test_trades_only_account_counts_buys_as_contributions(db: Session, user: User) -> None:
    account = Account(user_id=user.id, name="Trades only", broker="X", currency="USD", track_cash=False)
    db.add(account)
    db.add(FxRate(base="USD", quote="CHF", rate_date=D(2025, 1, 1), rate=Decimal("0.9"), source=PriceSource.SEED))
    db.commit()
    ingest_transactions(
        db,
        user_id=user.id,
        account_id=account.id,
        source=ImportSource.MANUAL,
        transactions=[
            StandardTransaction(
                date=D(2025, 1, 2),
                type=TransactionType.BUY,
                symbol="XYZ",
                quantity=Decimal(2),
                unit_price=Decimal(50),
                currency="USD",
            )
        ],
    )
    summary = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=AS_OF).summary()
    # No market data: valued at the last trade price, no negative cash.
    assert summary.net_worth == Decimal("100.00")
    assert summary.cash == Decimal("0.00")
    assert summary.net_contributions == Decimal("100.00")
    assert summary.market.unpriced_assets == 1


def test_missing_fx_rate_is_reported_not_guessed(db: Session, user: User, account: Account) -> None:
    ingest_transactions(
        db,
        user_id=user.id,
        account_id=account.id,
        source=ImportSource.MANUAL,
        transactions=[
            StandardTransaction(date=D(2025, 1, 2), type=TransactionType.DEPOSIT, amount=Decimal(100), currency="SEK")
        ],
    )
    summary = PortfolioEngine(db, user_id=user.id, base_currency="CHF", as_of=AS_OF).summary()
    assert summary.net_worth == Decimal("0.00")
    assert any("SEK" in warning for warning in summary.warnings)


def test_tbsz_milestones() -> None:
    assert reduced_rate_from(2025) == D(2029, 1, 1)
    assert tax_free_from(2025) == D(2031, 1, 1)


def test_tbsz_account_requires_vintage(db: Session, user: User) -> None:
    db.add(Account(user_id=user.id, name="Bad TBSZ", broker="Erste", currency="HUF", account_type=AccountType.TBSZ))
    with pytest.raises(IntegrityError):
        db.commit()
