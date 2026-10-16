import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import ImportSource, TransactionType
from app.models import Account, Asset, Transaction, User
from app.parsers import SourceFile
from app.parsers.ibkr import IBKRActivityCSVParser
from app.schemas.standard import StandardTransaction
from app.services.ingestion import find_duplicates, ingest_transactions
from tests.conftest import fixture_bytes


def _ingest(db: Session, user: User, account: Account, transactions: list[StandardTransaction]) -> tuple[int, int]:
    outcome = ingest_transactions(
        db, user_id=user.id, account_id=account.id, transactions=transactions, source=ImportSource.FILE
    )
    return outcome.imported, outcome.duplicates


def _buy(day: int, quantity: str = "1", price: str = "10", external_id: str | None = None) -> StandardTransaction:
    return StandardTransaction(
        date=dt.date(2025, 1, day),
        type=TransactionType.BUY,
        symbol="ABC",
        quantity=Decimal(quantity),
        unit_price=Decimal(price),
        currency="USD",
        external_id=external_id,
    )


def test_reimporting_a_statement_is_idempotent(db: Session, user: User, account: Account) -> None:
    transactions = IBKRActivityCSVParser().run(SourceFile("s.csv", fixture_bytes("ibkr_activity.csv"))).transactions
    assert _ingest(db, user, account, transactions) == (len(transactions), 0)
    assert _ingest(db, user, account, transactions) == (0, len(transactions))
    assert db.scalar(select(func.count()).select_from(Transaction)) == len(transactions)


def test_identical_rows_in_one_file_are_both_kept(db: Session, user: User, account: Account) -> None:
    twins = [_buy(2), _buy(2)]
    assert _ingest(db, user, account, twins) == (2, 0)
    assert _ingest(db, user, account, twins) == (0, 2)


def test_overlapping_date_ranges_only_add_new_rows(db: Session, user: User, account: Account) -> None:
    january = [_buy(2), _buy(9, price="11"), _buy(16, price="12")]
    assert _ingest(db, user, account, january[:2]) == (2, 0)
    assert _ingest(db, user, account, january) == (1, 2)


def test_external_id_wins_over_content_changes(db: Session, user: User, account: Account) -> None:
    assert _ingest(db, user, account, [_buy(2, external_id="T1")]) == (1, 0)
    corrected = _buy(2, price="10.01", external_id="T1")
    assert find_duplicates(db, account.id, [corrected]) == [True]
    assert _ingest(db, user, account, [corrected]) == (0, 1)


def test_duplicates_are_scoped_to_the_account(db: Session, user: User, account: Account) -> None:
    other = Account(user_id=user.id, name="Other", broker="Lightyear", currency="EUR")
    db.add(other)
    db.commit()
    assert _ingest(db, user, account, [_buy(2)]) == (1, 0)
    assert _ingest(db, user, other, [_buy(2)]) == (1, 0)


def test_assets_are_shared_and_resolved_by_listing(db: Session, user: User, account: Account) -> None:
    _ingest(db, user, account, [_buy(2), _buy(3)])
    dividend = StandardTransaction(
        date=dt.date(2025, 2, 1), type=TransactionType.DIVIDEND, symbol="ABC", amount=Decimal("1.5"), currency="EUR"
    )
    _ingest(db, user, account, [dividend])
    assets = list(db.scalars(select(Asset)))
    assert [(a.symbol, a.currency) for a in assets] == [("ABC", "USD")]
    stored = db.scalar(select(Transaction).where(Transaction.type == TransactionType.DIVIDEND))
    assert stored is not None
    assert stored.asset_id == assets[0].id


def test_decimals_round_trip_exactly(db: Session, user: User, account: Account) -> None:
    precise = _buy(2, quantity="0.1234567891", price="1234.5678901234")
    _ingest(db, user, account, [precise])
    stored = db.scalar(select(Transaction))
    assert stored is not None
    assert stored.quantity == Decimal("0.1234567891")
    assert stored.unit_price == Decimal("1234.5678901234")
    assert isinstance(stored.amount, Decimal)
