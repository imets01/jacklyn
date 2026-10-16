import datetime as dt
import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.enums import AssetClass, TransactionType
from app.parsers import ColumnMappingConfig, GenericCSVParser, MappingField, SourceFile, detect_parser
from app.parsers.generic import build_table_preview, guess_columns, guess_transaction_type
from app.parsers.ibkr import IBKRActivityCSVParser, IBKRFlexXMLParser
from app.parsers.lightyear import LightyearCSVParser
from app.schemas.standard import cash_flow
from tests.conftest import fixture_bytes

T = TransactionType


def source(name: str) -> SourceFile:
    return SourceFile(name, fixture_bytes(name))


@pytest.mark.parametrize(
    ("name", "parser_key"),
    [
        ("ibkr_activity.csv", "ibkr_activity_csv"),
        ("ibkr_flex.xml", "ibkr_flex_xml"),
        ("lightyear.csv", "lightyear_csv"),
        ("erste_netbroker.csv", "erste_netbroker"),
    ],
)
def test_detects_known_brokers(name: str, parser_key: str) -> None:
    detection = detect_parser(source(name))
    assert detection is not None
    assert detection.parser.key == parser_key


def test_unknown_csv_is_not_claimed_by_a_preset() -> None:
    assert detect_parser(source("revolut_trading.csv")) is None


def test_ibkr_activity_statement() -> None:
    result = IBKRActivityCSVParser().run(source("ibkr_activity.csv"))
    types = [t.type for t in result.transactions]
    assert result.errors == []
    assert types.count(T.BUY) == 2
    assert types.count(T.SELL) == 1
    assert types.count(T.FX_CONVERSION) == 2
    assert types.count(T.FEE) == 2  # FX commission + market data fee
    assert {T.DIVIDEND, T.TAX, T.DEPOSIT, T.INTEREST} <= set(types)
    assert any("Equity and Index Options" in warning for warning in result.warnings)

    aapl = next(t for t in result.transactions if t.type is T.BUY and t.symbol == "AAPL")
    assert aapl.date == dt.date(2025, 1, 6)
    assert aapl.quantity == Decimal(10)
    assert aapl.unit_price == Decimal("243.15")
    assert aapl.amount == Decimal("2431.5")
    assert aapl.fee == Decimal(1)
    assert aapl.isin == "US0378331005"
    assert aapl.exchange == "NASDAQ"

    sell = next(t for t in result.transactions if t.type is T.SELL)
    assert sell.quantity == Decimal(4)
    assert sell.amount == Decimal("952.4")

    legs = {t.currency: t.amount for t in result.transactions if t.type is T.FX_CONVERSION}
    assert legs == {"USD": Decimal(5000), "CHF": Decimal("-4535.5")}

    tax = next(t for t in result.transactions if t.type is T.TAX)
    assert (tax.symbol, tax.isin, tax.amount) == ("AAPL", "US0378331005", Decimal("0.38"))
    assert result.account_hint is not None
    assert result.account_hint.external_account_id == "U1234567"
    assert result.account_hint.currency == "CHF"


def test_ibkr_flex_xml() -> None:
    result = IBKRFlexXMLParser().run(source("ibkr_flex.xml"))
    assert result.errors == []
    assert len(result.transactions) == 8  # CLOSED_LOT and SUMMARY rows are skipped
    vwra = next(t for t in result.transactions if t.symbol == "VWRA")
    assert vwra.asset_class is AssetClass.ETF
    assert vwra.external_id == "T502"
    assert vwra.fee == Decimal("2.5")
    ids = {t.external_id for t in result.transactions}
    assert {"T501", "T503:USD", "T503:CHF", "T503:fee", "C7001", "C7002", "C7003"} <= ids


def test_lightyear_statement() -> None:
    detection = detect_parser(source("lightyear.csv"))
    assert detection is not None
    result = detection.parser.run(source("lightyear.csv"))
    assert result.errors == []
    assert len(result.transactions) == 8
    first = result.transactions[0]
    assert (first.date, first.type, first.amount) == (dt.date(2025, 1, 2), T.DEPOSIT, Decimal("1000.00"))
    conversion = [t for t in result.transactions if t.type is T.FX_CONVERSION]
    assert [(t.currency, t.amount) for t in conversion] == [("EUR", Decimal("-199.30")), ("USD", Decimal("205.48"))]
    nvda = next(t for t in result.transactions if t.type is T.BUY and t.symbol == "NVDA")
    assert nvda.quantity == Decimal("1.4")
    assert nvda.amount == Decimal("193.90")  # net = quantity x price; the fee is separate
    assert nvda.fee == Decimal("0.20")


def test_lightyear_cash_matches_net_amounts() -> None:
    """Lightyear's gross already includes fees on buys and conversions - fees must not be counted twice."""
    result = LightyearCSVParser().run(source("lightyear.csv"))
    cash: dict[str, Decimal] = {}
    for t in result.transactions:
        flow = cash_flow(t.type, t.amount, t.fee, t.tax, has_asset=bool(t.symbol or t.isin))
        cash[t.currency] = cash.get(t.currency, Decimal(0)) + flow
    # EUR: +1000 deposit (top-up fee not deducted) - 691.20 buy - 200.00 conversion + 0.85 interest
    assert cash["EUR"] == Decimal("109.65")
    # USD: +205.48 conversion - 194.10 buy + 0.07 net dividend + 59.94 net sale
    assert cash["USD"] == Decimal("71.39")


def test_erste_netbroker_cp1250_semicolons_and_comma_decimals() -> None:
    src = source("erste_netbroker.csv")
    assert src.encoding in {"cp1250", "windows-1250"}
    assert src.table.delimiter == ";"
    assert src.table.detect_header_row() == 4  # preamble lines skipped
    detection = detect_parser(src)
    assert detection is not None
    result = detection.parser.run(src)
    assert result.errors == []
    otp = result.transactions[0]
    assert otp.type is T.BUY
    assert otp.date == dt.date(2025, 1, 8)
    assert otp.unit_price == Decimal("25120.00")
    assert otp.amount == Decimal("1004800.00")
    assert otp.fee == Decimal("3516.80")
    assert otp.isin == "HU0000061726"
    assert otp.name == "OTP Bank Nyrt."
    assert result.transactions[2].type is T.SELL
    dividend = result.transactions[3]
    assert (dividend.type, dividend.amount, dividend.currency) == (T.DIVIDEND, Decimal("20000.00"), "HUF")


def test_generic_mapper_guesses_and_parses_unknown_csv() -> None:
    src = source("revolut_trading.csv")
    preview = build_table_preview(src.table)
    columns = preview.suggested.columns
    assert columns[MappingField.DATE] == "Date"
    assert columns[MappingField.SYMBOL] == "Ticker"
    assert columns[MappingField.UNIT_PRICE] == "Price per share"
    assert columns[MappingField.AMOUNT] == "Total Amount"
    assert preview.distinct_type_values == ["BUY - MARKET", "CASH TOP-UP", "SELL - MARKET", "DIVIDEND", "CUSTODY FEE"]

    result = GenericCSVParser(preview.suggested).run(src)
    assert result.errors == []
    assert [t.type for t in result.transactions] == [T.BUY, T.DEPOSIT, T.SELL, T.DIVIDEND, T.FEE]
    assert result.transactions[0].unit_price == Decimal("415.20")
    assert result.transactions[4].amount == Decimal("0.98")


def test_generic_mapper_reports_unmapped_types_per_row() -> None:
    config = ColumnMappingConfig(
        columns={
            MappingField.DATE: "Date",
            MappingField.TYPE: "Type",
            MappingField.AMOUNT: "Total Amount",
            MappingField.CURRENCY: "Currency",
            MappingField.SYMBOL: "Ticker",
            MappingField.QUANTITY: "Quantity",
        },
        type_map={"CASH TOP-UP": T.DEPOSIT},
    )
    csv = (
        b"Date,Type,Ticker,Quantity,Total Amount,Currency\n"
        b"2025-01-01,CASH TOP-UP,,,100,EUR\n"
        b"2025-01-02,STAKING,,,5,EUR\n"
    )
    result = GenericCSVParser(config).run(SourceFile("x.csv", csv))
    assert len(result.transactions) == 1
    assert result.errors[0].row == 3
    assert "STAKING" in result.errors[0].message


def test_generic_mapper_missing_requirements() -> None:
    result = GenericCSVParser(ColumnMappingConfig()).run(SourceFile("x.csv", b"a,b\n1,2\n"))
    assert result.transactions == []
    assert {e.message for e in result.errors} >= {"Map a date column."}


def test_xlsx_typed_cells_are_not_reinterpreted_with_a_comma_separator() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Account statement export"])
    sheet.append([])
    sheet.append(["Trade date", "Action", "Symbol", "Shares", "Price", "Commission", "Currency"])
    sheet.append([dt.datetime(2025, 3, 4), "Buy", "SAP", 3, 231.15, 1.5, "EUR"])
    sheet.append([dt.datetime(2025, 3, 5), "Sell", "SAP", 1.5, 1234.5, 0, "EUR"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    src = SourceFile("export.xlsx", buffer.getvalue())
    assert src.kind == "xlsx"
    preview = build_table_preview(src.table)
    assert preview.header_row == 2
    config = preview.suggested.model_copy(update={"decimal_separator": ","})
    result = GenericCSVParser(config).run(src)
    assert result.errors == []
    buy, sell = result.transactions
    assert (buy.date, buy.type, buy.quantity, buy.unit_price, buy.fee) == (
        dt.date(2025, 3, 4),
        T.BUY,
        Decimal(3),
        Decimal("231.15"),
        Decimal("1.5"),
    )
    assert (sell.type, sell.quantity, sell.unit_price) == (T.SELL, Decimal("1.5"), Decimal("1234.5"))


def test_guess_columns_handles_german_and_hungarian_headers() -> None:
    guessed = guess_columns(["Buchungsdatum", "Wertpapier", "Stück", "Kurs", "Währung", "Gebühren"])
    assert guessed[MappingField.DATE] == "Buchungsdatum"
    assert guessed[MappingField.QUANTITY] == "Stück"
    assert guessed[MappingField.UNIT_PRICE] == "Kurs"
    assert guessed[MappingField.CURRENCY] == "Währung"
    assert guessed[MappingField.FEE] == "Gebühren"
    assert guess_columns(["Dátum", "Mennyiség", "Árfolyam"])[MappingField.QUANTITY] == "Mennyiség"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Vétel", T.BUY), ("SELL - LIMIT", T.SELL), ("Withholding tax", T.TAX), ("Osztalék", T.DIVIDEND), ("??", None)],
)
def test_guess_transaction_type(raw: str, expected: TransactionType | None) -> None:
    assert guess_transaction_type(raw) is expected


def test_html_table_disguised_as_xls() -> None:
    html = (
        "<html><body><table><tr><th>Date</th><th>Type</th><th>Amount</th><th>Currency</th></tr>"
        "<tr><td>2025-01-02</td><td>Deposit</td><td>1 000,00</td><td>HUF</td></tr></table></body></html>"
    )
    src = SourceFile("statement.xls", html.encode("utf-8"))
    assert src.kind == "html"
    preview = build_table_preview(src.table)
    result = GenericCSVParser(preview.suggested).run(src)
    assert [(t.type, t.amount) for t in result.transactions] == [(T.DEPOSIT, Decimal("1000.00"))]
