"""Revolut trading statement: row types, rows skipped on purpose, and split stocks ending at Revolut's quantities."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ImportSource, PriceSource
from app.enums import TransactionType as T
from app.models import Account, Asset, AssetPrice, AssetSplit, User
from app.parsers import SourceFile, detect_parser
from app.parsers.revolut import SPLIT_NOTE, TRANSFER_NOTE, RevolutTradingParser
from app.services.ingestion import ingest_transactions
from app.services.portfolio import PortfolioEngine
from tests.conftest import fixture_bytes

MOVE = b"TRANSFER FROM REVOLUT TRADING LTD TO REVOLUT SECURITIES EUROPE UAB"
# Shaped like a real statement (2021 → 2026): buys before the 2022 splits, Revolut's own split rows, the 2023
# move between Revolut companies, a warrant closure, tax corrections and a withdrawal.
STATEMENT = b"""Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
2021-03-11T09:34:19.478431Z,,CASH TOP-UP,,,USD 200,USD,0.0033
2021-03-11T14:30:46.743338Z,TSLA,BUY - MARKET,0.07194141,USD 695.01,USD 50,USD,0.0033
2021-03-12T14:48:47.266150Z,GME,BUY - MARKET,0.10789814,USD 278.04,USD 30,USD,0.0033
2021-04-01T01:33:41.242120Z,,CUSTODY FEE,,,USD -0.02,USD,0.0033
2021-05-17T15:23:40.081176Z,GME,SELL - MARKET,0.081,USD 169.38,USD 13.72,USD,0.0035
2021-08-10T14:08:37.790529Z,AMZN,BUY - MARKET,0.04954617,USD 3350.41,USD 166,USD,0.0034
2021-09-10T04:53:24.477470Z,AMZN,DIVIDEND,,,USD 0.27,USD,0.0034
2022-06-06T05:22:14.286762Z,AMZN,STOCK SPLIT,0.94137723,,USD 0,USD,0.0028
2022-07-22T06:51:34.640314Z,GME,STOCK SPLIT,0.08069442,,USD 0,USD,0.0026
2022-08-25T08:30:39.735575Z,TSLA,STOCK SPLIT,0.14388282,,USD 0,USD,0.0025
2023-08-06T09:09:11.758382Z,AMZN,{move},0.9909234,,USD 0,USD,0.0029
2023-08-06T09:09:11.766575Z,GME,{move},0.10759256,,USD 0,USD,0.0029
2023-08-06T09:09:11.768409Z,TSLA,{move},0.21582423,,USD 0,USD,0.0029
2023-08-06T09:09:11.817181Z,,TRANSFER FROM REVOLUT BANK UAB TO REVOLUT SECURITIES EUROPE UAB,,,USD 1.14,USD,0.0029
2025-07-02T20:23:20.935328Z,AMZN,DIVIDEND TAX (CORRECTION),,,USD -0.14,USD,0.0030
2025-07-02T20:23:21.009126Z,AMZN,DIVIDEND TAX (CORRECTION),,,USD 0.14,USD,0.0030
2025-10-16T13:40:09.021628Z,GME.WS,POSITION CLOSURE,,,USD 0.03,USD,0.0030
2026-05-21T13:30:00.590Z,TSLA,SELL - MARKET,0.21582423,USD 422.33,USD 91.15,USD,0.0033
2026-06-01T11:57:14.785252Z,,CASH WITHDRAWAL,,,USD -10,USD,0.0033
""".replace(b"{move}", MOVE)


def parse(content: bytes = STATEMENT) -> object:
    source = SourceFile("trading-account-statement.csv", content)
    detection = detect_parser(source)
    assert detection is not None
    assert detection.parser.key == "revolut_trading"
    return detection.parser.run(source)


def test_every_row_type_is_understood() -> None:
    result = RevolutTradingParser().run(SourceFile("s.csv", STATEMENT))
    assert result.errors == []
    assert result.warnings == [SPLIT_NOTE, TRANSFER_NOTE]
    rows = [(t.type, t.symbol, t.amount) for t in result.transactions]
    assert rows == [
        (T.DEPOSIT, None, Decimal(200)),
        (T.BUY, "TSLA", Decimal(50)),
        (T.BUY, "GME", Decimal(30)),
        (T.FEE, None, Decimal("0.02")),
        (T.SELL, "GME", Decimal("13.72")),
        (T.BUY, "AMZN", Decimal(166)),
        (T.DIVIDEND, "AMZN", Decimal("0.27")),
        (T.TAX, "AMZN", Decimal("0.14")),
        (T.DIVIDEND, "AMZN", Decimal("0.14")),  # the correction reverses the tax
        (T.DIVIDEND, "GME.WS", Decimal("0.03")),  # a closed warrant position pays out its value
        (T.SELL, "TSLA", Decimal("91.15")),
        (T.WITHDRAWAL, None, Decimal(10)),
    ]
    buy = result.transactions[1]
    assert (buy.quantity, buy.unit_price, buy.currency, buy.date) == (
        Decimal("0.07194141"),
        Decimal("695.01"),
        "USD",
        dt.date(2021, 3, 11),
    )
    assert result.account_hint is not None
    assert result.account_hint.broker == "Revolut"


def test_dollar_signs_and_other_layouts() -> None:
    result = RevolutTradingParser().run(SourceFile("r.csv", fixture_bytes("revolut_trading.csv")))
    assert result.errors == []
    assert [t.type for t in result.transactions] == [T.BUY, T.DEPOSIT, T.SELL, T.DIVIDEND, T.FEE]
    assert result.transactions[0].unit_price == Decimal("415.20")
    assert result.transactions[4].amount == Decimal("0.98")
    unknown = STATEMENT + b"2026-07-01T10:00:00Z,,STAKING REWARD,,,USD 1,USD,1\n"
    assert (
        "Unknown Revolut transaction type 'STAKING REWARD'"
        in RevolutTradingParser().run(SourceFile("s.csv", unknown)).errors[0].message
    )


def test_split_stocks_end_at_revolut_quantities(db: Session, user: User, account: Account) -> None:
    """Revolut's split rows are skipped; Jacklyn's own split handling must land on the same share counts."""
    result = RevolutTradingParser().run(SourceFile("s.csv", STATEMENT))
    ingest_transactions(
        db, user_id=user.id, account_id=account.id, transactions=result.transactions, source=ImportSource.FILE
    )
    splits = {"AMZN": (dt.date(2022, 6, 6), 20), "GME": (dt.date(2022, 7, 22), 4), "TSLA": (dt.date(2022, 8, 25), 3)}
    # Split-adjusted closes on the buy dates, as Yahoo has them.
    closes = {"AMZN": "167.52", "GME": "66.25", "TSLA": "231.67"}
    assets = {asset.symbol: asset for asset in db.scalars(select(Asset))}
    for symbol, (day, ratio) in splits.items():
        asset = assets[symbol]
        db.add(AssetSplit(asset_id=asset.id, split_date=day, ratio=Decimal(ratio)))
        db.add(
            AssetPrice(
                asset_id=asset.id,
                price_date=dt.date(2021, 3, 1),
                close=Decimal(closes[symbol]),
                source=PriceSource.YFINANCE,
            )
        )
    db.commit()

    # Before the 2026 TSLA sale: the share counts Revolut itself listed when it moved the account in 2023.
    engine = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=dt.date(2023, 8, 6))
    positions = engine.replay()[account.id].positions
    held = {assets_by_id.symbol: positions[assets_by_id.id].quantity for assets_by_id in assets.values()}
    assert held == {"AMZN": Decimal("0.9909234"), "GME": Decimal("0.10759256"), "TSLA": Decimal("0.21582423")}

    engine = PortfolioEngine(db, user_id=user.id, base_currency="USD", as_of=dt.date(2026, 10, 1))
    assert engine.replay()[account.id].positions[assets["TSLA"].id].quantity == 0
