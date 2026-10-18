"""Erste NetBroker daily reports: parsing, sub-account routing and the multi-file import.

The fixtures are generated: anonymized copies of the real layouts, values at the same columns as NetBroker's
merged-cell sheets (a value often sits a few columns off its header).
"""

import datetime as dt
import io
from collections.abc import Callable
from decimal import Decimal
from typing import Any, ClassVar

import pandas as pd
import pytest
import yfinance
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.enums import AssetClass, TransactionType
from app.parsers import SourceFile, detect_parser
from app.parsers.erste_reports import ErsteDailyReportParser
from app.services import market_data
from tests.conftest import fixture_bytes

Cells = dict[int, Any]
CLIENT = "1234567"


def serial(day: dt.date) -> int:
    return (day - dt.date(1899, 12, 30)).days


def workbook(rows: list[Cells]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for index, cells in enumerate(rows, start=1):
        for column, value in cells.items():
            sheet.cell(row=index, column=column + 1, value=value)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def preamble(title: str) -> list[Cells]:
    return [{0: "Tisztelt TESZT ELEK!\nÜgyfélkód: 1234567"}, {}, {}, {}, {0: "Az Ön részére..."}, {0: title}]


CASH_HEADER: Cells = {
    0: "Kereskedési nap",
    4: "Tranzakció azonosító",
    8: "Tranzakció",
    26: "Művelet",
    34: "Összérték",
    45: "Költség",
    53: "Költség devizaneme",
    66: "Összesen",
    77: "Ügyfél",
    104: "Végrehajtás időpontja³ ",
}


def cash_rows(day: dt.date, entries: list[tuple[str, str, str, str, int]]) -> list[Cells]:
    """entries: (section, transaction id, name, direction, amount)."""
    rows: list[Cells] = [CASH_HEADER, {}]
    section = None
    for name_of_section, transaction_id, name, direction, amount in entries:
        if name_of_section != section:
            section = name_of_section
            rows += [{0: f"{CLIENT} - {section} - MAGYAR FORINT"}]
        rows += [
            {
                0: serial(day),
                4: int(transaction_id),
                8: name,
                26: direction,
                34: amount,
                45: 0,
                53: "HUF",
                66: amount,
                104: serial(day) + 0.25,
            }
        ]
    return [*rows, {0: "Záró készlet mennyiség² (db):", 12: 0}, {0: "Terhelés összesen", 38: 0, 76: 0}]


def cash_report(day: dt.date, entries: list[tuple[str, str, str, str, int]]) -> bytes:
    return workbook(preamble("Pénzügyi tranzakciók") + cash_rows(day, entries))


def fund_report(day: dt.date, side: str, quantity: float, price: float, fee: int, transaction_id: str) -> bytes:
    rows = [
        *preamble("Befektetési jegyek"),
        {
            0: "Kereskedési nap",
            4: "Tranzakció azonosító",
            8: "Instrumentum neve",
            19: "Instrumentum azonosítója",
            30: "Tranzakció",
            38: "Mennyiség  (db)",
            51: "Ár/db",
            58: "Összérték",
            71: "Költség",
            82: "Levont adó",
            89: "Összesen",
            100: "Elszámolás napja*",
            108: "Kereskedési helyszín és azonosító",
        },
        {},
        {},
        {0: "Future befektetés", 102: "Végrehajtás időpontja³ "},
        {0: f"{CLIENT} - TBSZ 2024 - MAGYAR FORINT"},
        {},
        {
            0: serial(day),
            4: int(transaction_id),
            8: "Erste Stock Techno HUF R01 VTA",
            20: "AT0000A09GU1",
            30: side,
            40: quantity,
            49: price,
            58: quantity * price,
            71: fee,
            81: 0,
            89: quantity * price + fee,
            100: serial(day) + 1,
            108: "OTC",
        },
        {0: "---", 102: serial(day) + 1.5},
        {},
        {0: "Záró készlet mennyiség² (db)", 13: quantity},
        {0: "Vétel összesen", 60: quantity * price, 72: fee, 89: quantity * price + fee},
    ]
    return workbook(rows)


SHARE_HEADER: Cells = {
    0: "Kereskedési nap",
    4: "Tranzakció azonosító",
    8: "Instrumentum neve",
    25: "Instrumentum azonosítója",
    35: "Tranzakció",
    47: "Megbízás típusa",
    55: "Mennyiség\n (db)",
    64: "Ár/darab",
    71: "Instrumentum devizaneme",
    81: "Devizaárfolyam",
    91: "Összérték",
    97: "Összesen",
    107: "Kereskedési helyszín és azonosító",
}
FX_HEADER: Cells = {
    0: "Kereskedési nap",
    3: "Tranzakció azonosító",
    6: "Instrumentum neve",
    17: "Tranzakció",
    29: "Terhelt devizanem",
    37: "Terhelt deviza mennyiség",
    45: "Jóváírt devizanem",
    53: "Jóváírt deviza mennyiség",
    67: "Árfolyam",
    78: "Felár",
    89: "Költség",
    97: "Elszámolás napja",
    106: "Kereskedési helyszín és azonosító",
}


def share_report(day: dt.date, *, with_cash_table: bool = False) -> bytes:
    rows = [
        *preamble("Külföldi részvény"),
        SHARE_HEADER,
        {},
        {},
        {0: "Elszámolás napja", 87: "Költség"},
        {104: "Végrehajtás időpontja³"},
        {},
        {0: f"{CLIENT} - TBSZ 2024 - EURO"},
        {
            0: serial(day),
            4: 192654598,
            8: "iShares Core S&P 500 UCITS ETF Acc",
            25: "IE00B5BMR087",
            35: "Vétel",
            47: "Limitáras",
            55: 8,
            64: 491.62,
            71: "EUR",
            81: 1,
            87: 3932.96,
            97: 3950.66,
            107: "XETRA-Frankfurt - XETR",
        },
        {},
        {0: serial(day) + 2, 87: 17.7, 104: serial(day) + 0.4},
        {},
        {},
        {0: "Záró készlet mennyiség² (db):", 13: 8},
        {},
        {},
        {0: "Befektetési szolgáltatási tevékenységhez kapcsolódó devizakonverzió"},
        {},
        FX_HEADER,
        {},
        {78: "Felár devizaneme", 89: "Felár %"},
        {},
        {99: "Végrehajtás időpontja³ "},
        {0: f"{CLIENT} - TBSZ 2024"},
        {
            0: serial(day),
            3: 192631502,
            6: "MAGYAR FORINT",
            17: "Vétel",
            31: "HUF",
            37: 1590675,
            45: "EUR",
            53: 4002,
            67: 397.47,
            89: 0,
            97: serial(day) + 2,
            106: "ERSTE",
        },
        {103: serial(day) + 0.35},
        {},
        {0: "Záró készlet mennyiség² (db):", 44: 34325, 61: 51.34},
    ]
    if with_cash_table:
        transfer = ("TBSZ 2024", "193155740", "Pénz átvezetés ügyfelek között", "jóváírás", 630000)
        rows += [{}, {}, {0: "Pénzügyi tranzakciók"}, *cash_rows(day, [transfer])]
    return workbook(rows)


DAY = dt.date(2024, 3, 11)
CASH = cash_report(
    DAY,
    [
        ("Normál", "192583123", "Átvezetés ERSTE Bankból", "jóváírás", 1600000),
        ("Normál", "192583125", "Pénz átvezetés ügyfelek között", "terhelés", 1600000),
        ("TBSZ 2024", "192583125", "Pénz átvezetés ügyfelek között", "jóváírás", 1600000),
    ],
)
FUND_BUY = fund_report(DAY, "Vétel", 0.153, 78868.65, 305, "289325510")
SHARES = share_report(DAY)


def run(content: bytes) -> Any:
    source = SourceFile("Riport.xlsx", content)
    detection = detect_parser(source)
    assert detection is not None
    assert detection.parser.key == "erste_daily_report"
    return detection.parser.run(source)


def test_only_erste_reports_are_detected() -> None:
    parser = ErsteDailyReportParser()
    for content in (CASH, FUND_BUY, SHARES):
        assert parser.detect(SourceFile("Riport.xlsx", content)) == 0.95
    for name in ("ibkr_activity.csv", "lightyear.csv", "erste_netbroker.csv", "revolut_trading.csv"):
        assert parser.detect(SourceFile(name, fixture_bytes(name))) == 0.0


def test_cash_movements_are_tagged_with_their_sub_account() -> None:
    result = run(CASH)
    assert not result.errors
    tagged = [(row.account, row.transaction.type, row.transaction.amount) for row in result.rows]
    assert tagged == [
        ("Normál", TransactionType.DEPOSIT, Decimal(1600000)),
        ("Normál", TransactionType.WITHDRAWAL, Decimal(1600000)),
        ("TBSZ 2024", TransactionType.DEPOSIT, Decimal(1600000)),
    ]
    assert result.rows[2].transaction.external_id == "192583125"
    assert result.rows[2].transaction.date == DAY
    tbsz = result.accounts["TBSZ 2024"]
    assert (tbsz.broker, tbsz.tbsz_year, tbsz.currency) == ("Erste Bank", 2024, "HUF")
    assert result.accounts["Normál"].tbsz_year is None


def test_fund_trades_settle_in_whole_forints() -> None:
    buy = run(FUND_BUY).rows[0]
    tx = buy.transaction
    assert buy.account == "TBSZ 2024"
    assert (tx.type, tx.isin, tx.asset_class, tx.currency) == (
        TransactionType.BUY,
        "AT0000A09GU1",
        AssetClass.FUND,
        "HUF",
    )
    assert (tx.quantity, tx.unit_price, tx.fee) == (Decimal("0.153"), Decimal("78868.65"), Decimal(305))
    assert tx.amount == Decimal(12067)  # 12 066.90345, rounded the way Erste books it

    sell = run(fund_report(DAY, "Eladás", 1.46, 125488.24, 0, "334121666")).rows[0].transaction
    assert (sell.type, sell.amount) == (TransactionType.SELL, Decimal(183213))


def test_etf_trades_take_the_fee_from_the_line_below_and_pair_currency_exchanges() -> None:
    result = run(SHARES)
    assert not result.errors
    buy, fx_out, fx_in = (row.transaction for row in result.rows)
    assert {row.account for row in result.rows} == {"TBSZ 2024"}
    assert (buy.type, buy.isin, buy.currency, buy.exchange) == (TransactionType.BUY, "IE00B5BMR087", "EUR", "XETR")
    assert (buy.quantity, buy.unit_price, buy.amount, buy.fee) == (
        Decimal(8),
        Decimal("491.62"),
        Decimal("3932.96"),
        Decimal("17.7"),
    )
    assert (fx_out.type, fx_out.currency, fx_out.amount) == (TransactionType.FX_CONVERSION, "HUF", Decimal(-1590675))
    assert (fx_in.currency, fx_in.amount) == ("EUR", Decimal(4002))
    assert fx_out.external_id == fx_in.external_id == "192631502"


def test_one_sheet_can_hold_an_etf_report_and_a_cash_report() -> None:
    result = run(share_report(DAY, with_cash_table=True))
    types = [row.transaction.type for row in result.rows]
    assert types == [
        TransactionType.BUY,
        TransactionType.FX_CONVERSION,
        TransactionType.FX_CONVERSION,
        TransactionType.DEPOSIT,
    ]


def _erste_tbsz(client: TestClient, year: int) -> dict[str, Any]:
    response = client.post(
        "/api/accounts",
        json={
            "name": f"Erste TBSZ {year}",
            "broker": "Erste Bank",
            "account_type": "tbsz",
            "tbsz_year": year,
            "currency": "HUF",
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _preview(client: TestClient, files: list[tuple[str, bytes]], **form: str) -> dict[str, Any]:
    response = client.post(
        "/api/import/preview", files=[("files", (name, content)) for name, content in files], data=form
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_a_folder_of_reports_imports_into_the_right_accounts(make_user: Callable[..., TestClient]) -> None:
    client = make_user()
    tbsz = _erste_tbsz(client, 2024)
    _erste_tbsz(client, 2025)  # another vintage must not attract 2024 rows
    files = [
        ("Riport.xlsx", CASH),
        ("Riport (1).xlsx", FUND_BUY),
        ("Riport (2).xlsx", SHARES),
        ("Riport (3).xlsx", FUND_BUY),  # downloaded twice
        ("statement.pdf", b"%PDF-1.4 not a report"),
    ]
    preview = _preview(client, files)
    assert (preview["status"], preview["file_count"], preview["filename"]) == ("parsed", 5, "5 files")
    assert [(s["filename"], s["reason"]) for s in preview["skipped_files"]] == [
        ("Riport (3).xlsx", "Same file as Riport (1).xlsx"),
        ("statement.pdf", "Not a CSV, Excel or XML file"),
    ]
    groups = {group["label"]: group for group in preview["groups"]}
    assert groups["TBSZ 2024"]["suggested_account_id"] == tbsz["id"]
    assert groups["TBSZ 2024"]["summary"]["new"] == 5  # deposit, fund buy, ETF buy, two FX legs
    assert groups["Normál"]["suggested_account_id"] is None  # the pass-through account is left out by default

    key = groups["TBSZ 2024"]["key"]
    rows = [row["transaction"] for row in preview["transactions"] if row["group"] == key]
    committed = client.post(
        "/api/import/commit",
        json={"account_id": tbsz["id"], "transactions": rows, "parser_key": "erste_daily_report"},
    )
    assert committed.json()["imported"] == 5

    holdings = client.get("/api/portfolio/holdings", params={"account_id": tbsz["id"], "base": "HUF"}).json()
    assert {h["isin"]: Decimal(h["quantity"]) for h in holdings["holdings"]} == {
        "AT0000A09GU1": Decimal("0.153"),
        "IE00B5BMR087": Decimal(8),
    }
    cash = {c["currency"]: Decimal(c["amount"]) for c in holdings["cash"]}
    assert cash == {"HUF": Decimal(1600000 - 12067 - 305 - 1590675), "EUR": Decimal("4002") - Decimal("3950.66")}

    again = _preview(client, files[:3])
    assert {g["label"]: g["summary"]["duplicates"] for g in again["groups"]}["TBSZ 2024"] == 5

    # Choosing an account for a group re-checks its duplicates against that account.
    chosen = _preview(client, files[:1], group_accounts=f'{{"{groups["Normál"]["key"]}": {tbsz["id"]}}}')
    normal = next(g for g in chosen["groups"] if g["label"] == "Normál")
    assert normal["suggested_account_id"] == tbsz["id"]


def test_files_nobody_recognizes_are_listed(make_user: Callable[..., TestClient]) -> None:
    client = make_user()
    preview = _preview(client, [("a.csv", b"foo;bar\n1;2\n"), ("b.csv", b"x,y\n3,4\n")])
    assert preview["status"] == "unsupported"
    assert len(preview["skipped_files"]) == 2


def test_a_multi_account_flex_upload_is_routed_by_account_number(make_user: Callable[..., TestClient]) -> None:
    client = make_user()
    linked = client.post(
        "/api/accounts",
        json={"name": "IBKR", "broker": "Interactive Brokers", "currency": "CHF", "external_account_id": "U1234567"},
    ).json()
    second = (
        '<FlexStatement accountId="U7654321"><AccountInformation accountId="U7654321" currency="EUR" />'
        '<CashTransactions><CashTransaction accountId="U7654321" currency="EUR" description="CASH RECEIPTS" '
        'dateTime="20250110" amount="2500" type="Deposits/Withdrawals" transactionID="8001" levelOfDetail="DETAIL" />'
        "</CashTransactions></FlexStatement></FlexStatements>"
    )
    xml = fixture_bytes("ibkr_flex.xml").decode().replace("</FlexStatements>", second).encode()
    preview = _preview(client, [("flex.xml", xml)])
    groups = {group["label"]: group["suggested_account_id"] for group in preview["groups"]}
    assert groups == {"U1234567": linked["id"], "U7654321": None}


class FakeSearch:
    RESULTS: ClassVar[dict[str, list[str]]] = {
        "IE00BMC38736": ["SMH.L", "IE00BMC38736.SG"],
        "VanEck Semiconductor UCITS ETF": ["SMH.L", "VVSM.DE", "SMH.PA"],
    }

    def __init__(self, query: str, **_: Any) -> None:
        self.quotes = [{"symbol": symbol} for symbol in self.RESULTS.get(query, [])]


class FakeListing:
    # (currency, closes around the trade date); ".SG" lines have a quote but no history.
    DATA: ClassVar[dict[str, tuple[str, list[float]]]] = {
        "SMH.L": ("USD", [101.0, 102.0]),
        "IE00BMC38736.SG": ("EUR", []),
        "VVSM.DE": ("EUR", [100.5, 101.1]),
        "SMH.PA": ("EUR", [100.4, 101.0]),
        "SMH.DE": ("EUR", [40.0, 41.0]),  # a different fund under the same base symbol
    }

    def __init__(self, ticker: str) -> None:
        if ticker not in self.DATA:
            raise KeyError(ticker)
        self.currency, self.closes = self.DATA[ticker]
        self.history_metadata = {"currency": self.currency}

    def history(self, **_: Any) -> pd.DataFrame:
        return pd.DataFrame({"Close": self.closes})


def test_an_isin_finds_the_listing_that_traded_near_the_price_paid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance, "Search", FakeSearch)
    monkeypatch.setattr(yfinance, "Ticker", FakeListing)
    day, price = dt.date(2026, 9, 30), Decimal("100.86")

    def find(**options: Any) -> str | None:
        return market_data.find_listing_for_isin(
            "IE00BMC38736", "VanEck Semiconductor UCITS ETF", "EUR", day, price, **options
        )

    assert find() == "VVSM.DE"  # USD line, no-history line and a look-alike priced 40 are all skipped
    assert find(venue="XPAR") == "SMH.PA"  # the venue actually traded on wins
    assert find(exclude="VVSM.DE") == "SMH.PA"
    assert market_data.find_listing_for_isin("IE00BMC38736", None, "EUR", day, Decimal(500)) is None
