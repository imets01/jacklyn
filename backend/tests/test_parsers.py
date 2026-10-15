from decimal import Decimal

import pytest

from app.models import Institution, TransactionType
from app.parsers import (
    ColumnMapping,
    ErsteNetBrokerParser,
    GenericCSVParser,
    IbkrActivityParser,
    LightyearParser,
    ParsedTransaction,
    detect_parser,
    suggest_mapping,
)
from app.parsers.csv_utils import build_sample, decode_bytes
from app.parsers.normalize import build_transaction, guess_transaction_type
from app.services.fingerprint import fingerprints
from tests.conftest import fixture_bytes


def sample(name: str):
    return build_sample(name, decode_bytes(fixture_bytes(name)))


@pytest.mark.parametrize(
    ("fixture", "parser"),
    [
        ("ibkr_activity.csv", IbkrActivityParser),
        ("lightyear_statement.csv", LightyearParser),
        ("erste_netbroker.csv", ErsteNetBrokerParser),
    ],
)
def test_detection(fixture: str, parser: type) -> None:
    detection = detect_parser(sample(fixture))
    assert detection is not None and detection.parser is parser


def test_unknown_layout_is_not_claimed() -> None:
    assert detect_parser(sample("custom_broker.csv")) is None


def test_ibkr_activity_statement() -> None:
    result = IbkrActivityParser().parse(decode_bytes(fixture_bytes("ibkr_activity.csv")))
    assert not result.errors, result.errors
    by_type: dict[TransactionType, list[ParsedTransaction]] = {}
    for tx in result.transactions:
        by_type.setdefault(tx.type, []).append(tx)

    vt = next(t for t in by_type[TransactionType.BUY] if t.symbol == "VT")
    assert vt.quantity == Decimal("20")
    assert vt.amount == Decimal("-2428")  # proceeds + commission
    assert vt.fee == Decimal("1")
    assert vt.isin == "US9220427424"

    sell = by_type[TransactionType.SELL][0]
    assert (
        sell.symbol == "AAPL" and sell.quantity == Decimal("5") and sell.amount == Decimal("1181")
    )

    fx_legs = {t.currency: t.amount for t in by_type[TransactionType.FX]}
    assert fx_legs == {"CHF": Decimal("2500"), "USD": Decimal("-2910")}

    assert by_type[TransactionType.DIVIDEND][0].symbol == "VT"
    assert by_type[TransactionType.TAX][0].amount == Decimal("-1.56")
    assert [t.amount for t in by_type[TransactionType.DEPOSIT]] == [Decimal("5000")]
    assert [t.amount for t in by_type[TransactionType.WITHDRAWAL]] == [Decimal("-750")]
    assert by_type[TransactionType.INTEREST][0].amount == Decimal("0.83")
    # totals/subtotals are skipped
    assert all(t.currency != "Total" for t in result.transactions)


def test_lightyear_statement() -> None:
    result = LightyearParser().parse(decode_bytes(fixture_bytes("lightyear_statement.csv")))
    assert len(result.transactions) == 6
    assert len(result.errors) == 1 and "Mystery" in result.errors[0].message
    buy = result.transactions[1]
    assert buy.type is TransactionType.BUY
    assert buy.amount == Decimal("-560.00")
    assert buy.quantity == Decimal("4.2105")
    assert buy.external_id == "LY-ORD-0002"
    deposit, withdrawal = result.transactions[0], result.transactions[5]
    assert deposit.amount == Decimal("1000.00")
    assert withdrawal.amount == Decimal("-200.00")


def test_erste_cp1250_export() -> None:
    raw = fixture_bytes("erste_netbroker.csv").decode("utf-8").encode("cp1250")
    text = decode_bytes(raw)
    result = ErsteNetBrokerParser().parse(text)
    assert not result.errors, result.errors
    types = [t.type for t in result.transactions]
    assert types == [
        TransactionType.DEPOSIT,
        TransactionType.BUY,
        TransactionType.BUY,
        TransactionType.DIVIDEND,
        TransactionType.SELL,
    ]
    otp = result.transactions[1]
    assert otp.price == Decimal("29850.00")
    assert otp.amount == Decimal("-119400.00")
    assert otp.isin == "HU0000061726"
    assert otp.trade_date.isoformat() == "2026-01-09"
    assert ErsteNetBrokerParser.institution is Institution.ERSTE


def test_generic_parser_with_mapping() -> None:
    mapping = ColumnMapping(
        columns={
            "trade_date": "When",
            "type": "What",
            "symbol": "Paper",
            "quantity": "Units",
            "price": "Unit price",
            "amount": "Total",
            "currency": "Cur",
            "external_id": "Ref",
        },
        date_format="%d.%m.%Y",
        decimal_separator=",",
    )
    result = GenericCSVParser(mapping).parse(decode_bytes(fixture_bytes("custom_broker.csv")))
    assert not result.errors
    assert [t.type for t in result.transactions] == [
        TransactionType.BUY,
        TransactionType.BUY,
        TransactionType.DIVIDEND,
    ]
    assert result.transactions[0].amount == Decimal("-397.20")


def test_generic_reports_missing_columns() -> None:
    mapping = ColumnMapping(
        columns={"trade_date": "Nope", "type": "What", "amount": "Total"}, default_currency="EUR"
    )
    result = GenericCSVParser(mapping).parse(decode_bytes(fixture_bytes("custom_broker.csv")))
    assert result.errors and "Nope" in result.errors[0].message


def test_mapping_requires_core_fields() -> None:
    with pytest.raises(ValueError, match="trade_date"):
        ColumnMapping(columns={"type": "x", "amount": "y"}, default_currency="EUR")


def test_suggest_mapping_for_unknown_file() -> None:
    suggestion = suggest_mapping(sample("lightyear_statement.csv"))
    assert suggestion.columns["trade_date"] == "Date"
    assert suggestion.columns["isin"] == "ISIN"
    assert suggestion.columns["currency"] == "CCY"
    assert suggestion.date_format == "%d/%m/%Y %H:%M:%S"
    assert suggestion.type_map["Buy"] is TransactionType.BUY


def test_type_synonyms() -> None:
    assert guess_transaction_type("Market buy - AAPL") is TransactionType.BUY
    assert guess_transaction_type("Vétel") is TransactionType.BUY
    assert guess_transaction_type("Dividende") is TransactionType.DIVIDEND
    assert guess_transaction_type("???") is None


def test_amount_derived_and_signed() -> None:
    tx = build_transaction(
        row_number=1,
        ttype=TransactionType.BUY,
        trade_date=__import__("datetime").date(2026, 1, 1),
        currency="eur",
        amount=None,
        quantity=Decimal("3"),
        price=Decimal("10.50"),
        fee=Decimal("-1"),
    )
    assert tx.amount == Decimal("-32.50") and tx.fee == Decimal("1") and tx.currency == "EUR"


def test_fingerprints_stable_and_distinguish_identical_rows() -> None:
    text = decode_bytes(fixture_bytes("lightyear_statement.csv"))
    first = fingerprints(LightyearParser().parse(text).transactions)
    second = fingerprints(LightyearParser().parse(text).transactions)
    assert first == second

    tx = build_transaction(
        row_number=1,
        ttype=TransactionType.DEPOSIT,
        trade_date=__import__("datetime").date(2026, 1, 1),
        currency="EUR",
        amount=Decimal("10"),
    )
    a, b = fingerprints([tx, tx])
    assert a != b
