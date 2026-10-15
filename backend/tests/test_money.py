from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.money import FloatNotAllowedError, parse_decimal, quantize_money, to_decimal
from app.models import Account, AccountType, Institution, Transaction, TransactionType, User


def test_to_decimal_rejects_floats() -> None:
    with pytest.raises(FloatNotAllowedError):
        to_decimal(0.1)
    assert to_decimal("0.1") + to_decimal("0.2") == Decimal("0.3")


@pytest.mark.parametrize(
    ("raw", "dec", "thousands", "expected"),
    [
        ("1,234.56", ".", None, "1234.56"),
        ("1 234,56", ",", None, "1234.56"),
        ("1.234,56", ",", None, "1234.56"),
        ("150 000,00", ",", " ", "150000.00"),
        ("(12.50)", ".", None, "-12.50"),
        ("12.50-", ".", None, "-12.50"),
        ("− 3.10", ".", None, "-3.10"),
        ("CHF 1'250.00", ".", None, "1250.00"),
        ("+4.2", ".", None, "4.2"),
    ],
)
def test_parse_decimal(raw: str, dec: str, thousands: str | None, expected: str) -> None:
    assert parse_decimal(raw, dec, thousands) == Decimal(expected)


def test_parse_decimal_blank_and_garbage() -> None:
    assert parse_decimal("  ") is None
    with pytest.raises(ValueError):
        parse_decimal("abc1x2")


def test_quantize_money_per_currency() -> None:
    assert quantize_money(Decimal("10.005"), "EUR") == Decimal("10.00")  # banker's rounding
    assert quantize_money(Decimal("1234.5"), "HUF") == Decimal("1234")


def test_safe_decimal_roundtrip_is_exact(db) -> None:
    user = User(email="x@example.com", display_name="X", base_currency="EUR")
    db.add(user)
    db.flush()
    account = Account(
        user_id=user.id,
        name="A",
        institution=Institution.OTHER,
        account_type=AccountType.STANDARD,
        base_currency="EUR",
    )
    db.add(account)
    db.flush()
    precise = Decimal("12345678901234.0123456789")
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            type=TransactionType.DEPOSIT,
            trade_date=date(2026, 1, 1),
            amount=precise,
            currency="EUR",
            fingerprint="f",
        )
    )
    db.commit()
    db.expunge_all()
    stored = db.scalars(select(Transaction.amount)).one()
    assert stored == precise and isinstance(stored, Decimal)


def test_safe_decimal_rejects_float_on_write(db) -> None:
    user = User(email="y@example.com", display_name="Y", base_currency="EUR")
    db.add(user)
    db.flush()
    account = Account(user_id=user.id, name="A", institution=Institution.OTHER, base_currency="EUR")
    db.add(account)
    db.flush()
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            type=TransactionType.DEPOSIT,
            trade_date=date(2026, 1, 1),
            amount=0.1,
            currency="EUR",
            fingerprint="f",
        )
    )
    with pytest.raises(Exception, match="Float"):
        db.commit()
