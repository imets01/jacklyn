import datetime as dt
from decimal import Decimal

import pytest

from app.parsers.text import (
    ISO8601,
    NumberFormatError,
    detect_date_format,
    detect_decimal_separator,
    parse_date,
    parse_decimal,
)


@pytest.mark.parametrize(
    ("raw", "separator", "expected"),
    [
        ("1234.56", None, "1234.56"),
        ("1,234.56", None, "1234.56"),
        ("1.234,56", None, "1234.56"),
        ("1 234,56", None, "1234.56"),
        ("1 234,56", ",", "1234.56"),
        ("1'234.50", None, "1234.50"),
        ("12,5", None, "12.5"),
        ("1,234", None, "1234"),
        ("1.234", ",", "1234"),
        ("1.234", ".", "1.234"),
        ("(12.50)", None, "-12.50"),
        ("12.50-", None, "-12.50"),
        ("-$0.98", None, "-0.98"),
        ("$415.20", None, "415.20"),
        ("USD -12.50", None, "-12.50"),
        ("12,50 €", ",", "12.50"),
        ("CHF 1'000", None, "1000"),
        ("1.5E-3", None, "0.0015"),
        ("+3", None, "3"),
    ],
)
def test_parse_decimal(raw: str, separator: str | None, expected: str) -> None:
    assert parse_decimal(raw, separator) == Decimal(expected)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["", "  ", "-", "n/a", None])
def test_parse_decimal_blank(raw: str | None) -> None:
    assert parse_decimal(raw) is None


def test_parse_decimal_rejects_text() -> None:
    with pytest.raises(NumberFormatError):
        parse_decimal("twelve")


def test_parse_decimal_is_exact() -> None:
    assert parse_decimal("0.1") + parse_decimal("0.2") == Decimal("0.3")  # type: ignore[operator]


def test_detect_decimal_separator() -> None:
    assert detect_decimal_separator(["1 004 800,00", "3 516,80", "25 120,00"]) == ","
    assert detect_decimal_separator(["1,004,800.00", "3,516.80", "12.5"]) == "."
    assert detect_decimal_separator([]) == "."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-01-06", dt.date(2025, 1, 6)),
        ("2025-01-06, 10:31:02", dt.date(2025, 1, 6)),
        ("2025-01-10T14:32:11.123Z", dt.date(2025, 1, 10)),
        ("20250106", dt.date(2025, 1, 6)),
        ("2025.01.08.", dt.date(2025, 1, 8)),
        ("08.01.2025", dt.date(2025, 1, 8)),
        ("15/01/2025 08:00:00", dt.date(2025, 1, 15)),
    ],
)
def test_parse_date(raw: str, expected: dt.date) -> None:
    assert parse_date(raw) == expected


def test_detect_date_format_prefers_day_first_but_respects_evidence() -> None:
    assert detect_date_format(["03/01/2025", "04/01/2025"]) == "%d/%m/%Y"
    assert detect_date_format(["01/13/2025", "01/14/2025"]) == "%m/%d/%Y"
    assert detect_date_format(["2025-01-06", "2025-02-01T10:00:00"]) == ISO8601
    assert detect_date_format(["2025.01.08.", "2025.02.14."]) == "%Y.%m.%d."
