"""Startup seeder: a default user plus ~2 years of realistic multi-currency history.

The generated history is deterministic for a given ``today`` and goes through
the same normalisation (``build_transaction``) and fingerprinting as real
imports, so later importing an overlapping statement dedupes correctly.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.money import ZERO, quantize_money
from app.models import Account, AccountType, Asset, AssetClass, Institution, TransactionType, User
from app.parsers.base import ParsedTransaction
from app.parsers.normalize import build_transaction
from app.services.fingerprint import fingerprints
from app.services.fx import default_fx
from app.services.importer import persist_transactions

log = logging.getLogger(__name__)

MONTHS = 24
# Deterministic month-to-month price noise (no floats, no randomness).
_WIGGLE = [
    Decimal(x)
    for x in (
        "1.000",
        "1.018",
        "0.991",
        "1.027",
        "0.982",
        "1.009",
        "1.034",
        "0.976",
        "1.012",
        "0.995",
        "1.021",
        "0.988",
        "1.006",
        "1.029",
        "0.979",
        "1.015",
    )
]


@dataclass(frozen=True, slots=True)
class AssetSpec:
    symbol: str
    name: str
    isin: str
    asset_class: AssetClass
    currency: str
    exchange: str
    start_price: Decimal
    end_price: Decimal
    dividend_per_share: Decimal = ZERO  # per payment
    dividend_months: tuple[int, ...] = ()


def _d(value: str) -> Decimal:
    return Decimal(value)


ASSETS: dict[str, AssetSpec] = {
    s.symbol: s
    for s in (
        AssetSpec(
            "CHSPI",
            "iShares Core SPI ETF",
            "CH0237935652",
            AssetClass.ETF,
            "CHF",
            "SIX",
            _d("146.20"),
            _d("168.30"),
        ),
        AssetSpec(
            "NESN",
            "Nestlé SA",
            "CH0038863350",
            AssetClass.EQUITY,
            "CHF",
            "SIX",
            _d("96.50"),
            _d("82.40"),
            _d("3.05"),
            (4,),
        ),
        AssetSpec(
            "NOVN",
            "Novartis AG",
            "CH0012005267",
            AssetClass.EQUITY,
            "CHF",
            "SIX",
            _d("88.70"),
            _d("96.10"),
            _d("3.50"),
            (3,),
        ),
        AssetSpec(
            "VT",
            "Vanguard Total World Stock ETF",
            "US9220427424",
            AssetClass.ETF,
            "USD",
            "NYSE",
            _d("112.40"),
            _d("128.50"),
            _d("0.52"),
            (3, 6, 9, 12),
        ),
        AssetSpec(
            "AAPL",
            "Apple Inc.",
            "US0378331005",
            AssetClass.EQUITY,
            "USD",
            "NASDAQ",
            _d("226.00"),
            _d("248.00"),
            _d("0.26"),
            (2, 5, 8, 11),
        ),
        AssetSpec(
            "MSFT",
            "Microsoft Corp.",
            "US5949181045",
            AssetClass.EQUITY,
            "USD",
            "NASDAQ",
            _d("418.00"),
            _d("455.00"),
            _d("0.83"),
            (3, 6, 9, 12),
        ),
        AssetSpec(
            "VWCE",
            "Vanguard FTSE All-World UCITS ETF (Acc)",
            "IE00BK5BQT80",
            AssetClass.ETF,
            "EUR",
            "XETRA",
            _d("118.60"),
            _d("142.80"),
        ),
        AssetSpec(
            "EUNL",
            "iShares Core MSCI World UCITS ETF",
            "IE00B4L5Y983",
            AssetClass.ETF,
            "EUR",
            "XETRA",
            _d("98.20"),
            _d("108.40"),
        ),
        AssetSpec(
            "AGGH",
            "iShares Core Global Aggregate Bond UCITS ETF",
            "IE00BDBRDM35",
            AssetClass.BOND,
            "EUR",
            "XETRA",
            _d("5.12"),
            _d("5.40"),
        ),
        AssetSpec(
            "OTP",
            "OTP Bank Nyrt.",
            "HU0000061726",
            AssetClass.EQUITY,
            "HUF",
            "BSE",
            _d("22400"),
            _d("31500"),
            _d("371"),
            (6,),
        ),
        AssetSpec(
            "MOL",
            "MOL Nyrt.",
            "HU0000153937",
            AssetClass.EQUITY,
            "HUF",
            "BSE",
            _d("2820"),
            _d("2950"),
            _d("275"),
            (6,),
        ),
        AssetSpec(
            "RICHTER",
            "Richter Gedeon Nyrt.",
            "HU0000123096",
            AssetClass.EQUITY,
            "HUF",
            "BSE",
            _d("9650"),
            _d("10450"),
            _d("398"),
            (6,),
        ),
    )
}


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def _price(spec: AssetSpec, month_index: int) -> Decimal:
    """Price path from start to end over ``MONTHS`` with deterministic noise."""
    if month_index >= MONTHS:
        return spec.end_price
    trend = spec.start_price + (spec.end_price - spec.start_price) * month_index / MONTHS
    noisy = trend * _WIGGLE[(month_index + len(spec.symbol)) % len(_WIGGLE)]
    return noisy.quantize(Decimal("0.01") if spec.currency != "HUF" else Decimal("1"))


class _AccountBook:
    """Accumulates transactions for one account while tracking share counts."""

    def __init__(self, fractional: bool = False) -> None:
        self.txs: list[ParsedTransaction] = []
        self.shares: dict[str, Decimal] = defaultdict(lambda: ZERO)
        self.fractional = fractional

    def _add(self, **kwargs: object) -> None:
        self.txs.append(build_transaction(row_number=len(self.txs) + 1, **kwargs))  # type: ignore[arg-type]

    def deposit(self, when: date, amount: Decimal, ccy: str) -> None:
        self._add(
            ttype=TransactionType.DEPOSIT,
            trade_date=when,
            currency=ccy,
            amount=amount,
            description="Deposit",
        )

    def fx(self, when: date, amount: Decimal, from_ccy: str, to_ccy: str) -> Decimal:
        received = quantize_money(default_fx.convert(amount, from_ccy, to_ccy), to_ccy)
        desc = f"FX {from_ccy}→{to_ccy}"
        self._add(
            ttype=TransactionType.FX,
            trade_date=when,
            currency=from_ccy,
            amount=-amount,
            amount_sign="as_is",
            description=desc,
        )
        self._add(
            ttype=TransactionType.FX,
            trade_date=when,
            currency=to_ccy,
            amount=received,
            amount_sign="as_is",
            description=desc,
        )
        return received

    def buy(self, when: date, symbol: str, budget: Decimal, month_index: int, fee: Decimal) -> None:
        spec = ASSETS[symbol]
        price = _price(spec, month_index)
        step = Decimal("0.0001") if self.fractional else Decimal("1")
        qty = (budget / price).quantize(step, rounding=ROUND_DOWN)
        if qty <= ZERO:
            return
        amount = -quantize_money(qty * price + fee, spec.currency)
        self._add(
            ttype=TransactionType.BUY,
            trade_date=when,
            currency=spec.currency,
            amount=amount,
            quantity=qty,
            price=price,
            fee=fee,
            symbol=symbol,
            isin=spec.isin,
            asset_name=spec.name,
            asset_class=spec.asset_class,
            description=f"Buy {qty} {symbol}",
        )
        self.shares[symbol] += qty

    def dividends(self, when: date, withholding: Decimal) -> None:
        for symbol, qty in list(self.shares.items()):
            spec = ASSETS[symbol]
            if qty <= ZERO or when.month not in spec.dividend_months:
                continue
            gross = quantize_money(qty * spec.dividend_per_share, spec.currency)
            if gross <= ZERO:
                continue
            self._add(
                ttype=TransactionType.DIVIDEND,
                trade_date=when,
                currency=spec.currency,
                amount=gross,
                symbol=symbol,
                isin=spec.isin,
                asset_name=spec.name,
                description=f"{symbol} cash dividend {spec.dividend_per_share}/share",
            )
            tax = quantize_money(gross * withholding, spec.currency)
            if tax > ZERO:
                self._add(
                    ttype=TransactionType.TAX,
                    trade_date=when,
                    currency=spec.currency,
                    amount=tax,
                    symbol=symbol,
                    isin=spec.isin,
                    description=f"{symbol} withholding tax",
                )


def _months(today: date) -> list[tuple[int, date]]:
    first = _add_months(today.replace(day=1), -(MONTHS - 1))
    return [(i, _add_months(first, i)) for i in range(MONTHS)]


def _on(month_start: date, day: int, today: date) -> date | None:
    d = month_start.replace(day=day)
    return d if d <= today else None


def build_ibkr_swiss(today: date) -> list[ParsedTransaction]:
    book = _AccountBook()
    fee = Decimal("1.00")
    for i, m in _months(today):
        if (d := _on(m, 2, today)) is None:
            continue
        book.deposit(d, Decimal("3000"), "CHF")
        buy_day = _on(m, 6, today) or d
        book.buy(buy_day, "CHSPI", Decimal("1200"), i, fee)
        book.buy(buy_day, "NESN" if i % 2 else "NOVN", Decimal("600"), i, fee)
        usd = book.fx(buy_day, Decimal("1000"), "CHF", "USD")
        book.buy(buy_day, "VT", usd * Decimal("0.7"), i, fee)
        if i % 3 == 0:
            book.buy(buy_day, "AAPL", usd * Decimal("0.6"), i, fee)
        if (div_day := _on(m, 20, today)) is not None:
            book.dividends(div_day, withholding=Decimal("0.15"))
    return book.txs


def build_ibkr_tbsz(today: date, tbsz_year: int) -> list[ParsedTransaction]:
    """TBSZ: deposits only during the collection year, then held."""
    book = _AccountBook()
    fee = Decimal("600")
    for i, m in _months(today):
        if (d := _on(m, 3, today)) is None:
            continue
        if m.year == tbsz_year:
            book.deposit(d, Decimal("400000"), "HUF")
            buy_day = _on(m, 7, today) or d
            book.buy(buy_day, ("OTP", "MOL", "RICHTER")[i % 3], Decimal("180000"), i, fee)
            eur = book.fx(buy_day, Decimal("200000"), "HUF", "EUR")
            book.buy(buy_day, "EUNL", eur, i, Decimal("1.25"))
        if (div_day := _on(m, 22, today)) is not None:
            book.dividends(div_day, withholding=ZERO)  # no Hungarian tax inside TBSZ
    return book.txs


def build_lightyear(today: date) -> list[ParsedTransaction]:
    book = _AccountBook(fractional=True)
    for i, m in _months(today):
        if (d := _on(m, 1, today)) is None:
            continue
        book.deposit(d, Decimal("800"), "EUR")
        buy_day = _on(m, 4, today) or d
        book.buy(buy_day, "VWCE", Decimal("560"), i, ZERO)
        book.buy(buy_day, "AGGH", Decimal("100"), i, ZERO)
        usd = book.fx(buy_day, Decimal("100"), "EUR", "USD")
        book.buy(buy_day, "MSFT", usd, i, ZERO)
        if (int_day := _on(m, 28, today)) is not None and i > 0:
            book._add(
                ttype=TransactionType.INTEREST,
                trade_date=int_day,
                currency="EUR",
                amount=Decimal("2.40") + Decimal(i) * Decimal("0.15"),
                description="Interest on uninvested cash",
            )
        if (div_day := _on(m, 18, today)) is not None:
            book.dividends(div_day, withholding=Decimal("0.15"))
    return book.txs


def build_erste(today: date) -> list[ParsedTransaction]:
    book = _AccountBook()
    rotation = ("OTP", "RICHTER", "MOL")
    for i, m in _months(today):
        if (d := _on(m, 5, today)) is None:
            continue
        book.deposit(d, Decimal("150000"), "HUF")
        buy_day = _on(m, 9, today) or d
        book.buy(buy_day, rotation[i % 3], Decimal("135000"), i, Decimal("1000"))
        if (div_day := _on(m, 25, today)) is not None:
            book.dividends(div_day, withholding=Decimal("0.15"))
    return book.txs


def get_or_create_default_user(db: Session, settings: Settings) -> User:
    user = db.scalars(select(User).where(User.email == settings.default_user_email)).first()
    if user is None:
        user = User(
            email=settings.default_user_email,
            display_name="Jacklyn Demo",
            base_currency=settings.default_base_currency,
        )
        db.add(user)
        db.commit()
    return user


def seed_demo_data(db: Session, user: User, today: date | None = None) -> None:
    """Populate demo accounts for ``user`` if they have none yet."""
    today = today or date.today()
    if db.scalars(select(Account.id).where(Account.user_id == user.id)).first() is not None:
        return

    now = datetime.now(UTC)
    for spec in ASSETS.values():
        db.add(
            Asset(
                user_id=user.id,
                symbol=spec.symbol,
                name=spec.name,
                isin=spec.isin,
                asset_class=spec.asset_class,
                currency=spec.currency,
                exchange=spec.exchange,
                last_price=spec.end_price,
                last_price_at=now,
            )
        )

    tbsz_year = 2025
    plans: list[tuple[Account, list[ParsedTransaction]]] = [
        (
            Account(
                user_id=user.id,
                name="IBKR Swiss",
                institution=Institution.IBKR,
                account_type=AccountType.SWISS,
                base_currency="CHF",
                account_number="U1234567",
            ),
            build_ibkr_swiss(today),
        ),
        (
            Account(
                user_id=user.id,
                name=f"IBKR TBSZ {tbsz_year}",
                institution=Institution.IBKR,
                account_type=AccountType.TBSZ,
                tbsz_year=tbsz_year,
                base_currency="HUF",
                account_number="U7654321",
            ),
            build_ibkr_tbsz(today, tbsz_year),
        ),
        (
            Account(
                user_id=user.id,
                name="Lightyear",
                institution=Institution.LIGHTYEAR,
                account_type=AccountType.STANDARD,
                base_currency="EUR",
            ),
            build_lightyear(today),
        ),
        (
            Account(
                user_id=user.id,
                name="Erste NetBroker",
                institution=Institution.ERSTE,
                account_type=AccountType.STANDARD,
                base_currency="HUF",
                account_number="11600006-00000000",
            ),
            build_erste(today),
        ),
    ]
    db.flush()
    total = 0
    for account, txs in plans:
        db.add(account)
        db.flush()
        imported, _, _ = persist_transactions(db, user.id, account, txs, fingerprints(txs))
        total += imported
    db.commit()
    log.info("Seeded %d accounts with %d transactions for %s", len(plans), total, user.email)


def run_startup_seed(db: Session, settings: Settings) -> User:
    user = get_or_create_default_user(db, settings)
    if settings.seed_on_startup:
        seed_demo_data(db, user)
    return user
