"""Startup seeding: an unclaimed owner account and a realistic demo portfolio (first run only).

The owner has no password until first-run setup claims it (see app.api.auth), so a fresh instance
can't be used by anyone who doesn't hold the setup token.

Demo prices/FX are a deterministic synthetic history ending near realistic levels, so the dashboard
is alive offline. When live market data is enabled, yfinance replaces them with real history.
"""

import datetime as dt
import logging
import random
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.enums import AccountType, AssetClass, ImportSource, PriceSource, TransactionType
from app.models import Account, Asset, AssetPrice, FxRate, User
from app.schemas.standard import StandardTransaction
from app.security import passwords
from app.security.secrets import new_token
from app.services.ingestion import ingest_transactions

logger = logging.getLogger(__name__)
HISTORY_DAYS = 730
PRICE_QUANTUM = Decimal("0.01")
FX_QUANTUM = Decimal("0.000001")
SQRT3 = Decimal(3).sqrt()


def ensure_owner(session: Session, settings: Settings) -> User | None:
    """The admin account waiting to be claimed, created on an empty database. None once claimed."""
    if session.scalar(select(User.id).limit(1)) is None:
        session.add(
            User(
                email=settings.default_user_email,
                display_name=settings.default_user_name,
                base_currency=settings.default_base_currency,
                is_admin=True,
            )
        )
        session.commit()
        logger.info("Created the owner account (claimed during first-run setup)")
    return session.scalar(
        select(User).where(User.is_admin.is_(True), User.password_hash.is_(None)).order_by(User.id).limit(1)
    )


@dataclass(frozen=True)
class SeedAsset:
    symbol: str
    yf_ticker: str
    isin: str
    name: str
    asset_class: AssetClass
    currency: str
    start_price: str
    end_price: str
    daily_vol: str


SEED_ASSETS: tuple[SeedAsset, ...] = (
    SeedAsset("NESN", "NESN.SW", "CH0038863350", "Nestlé SA", AssetClass.STOCK, "CHF", "94", "84", "0.011"),
    SeedAsset("NOVN", "NOVN.SW", "CH0012005267", "Novartis AG", AssetClass.STOCK, "CHF", "91", "104", "0.011"),
    SeedAsset(
        "CHSPI", "CHSPI.SW", "CH0237935652", "iShares Core SPI ETF (CH)", AssetClass.ETF, "CHF", "151", "176", "0.008"
    ),
    SeedAsset("AAPL", "AAPL", "US0378331005", "Apple Inc.", AssetClass.STOCK, "USD", "226", "252", "0.016"),
    SeedAsset("MSFT", "MSFT", "US5949181045", "Microsoft Corp.", AssetClass.STOCK, "USD", "418", "512", "0.015"),
    SeedAsset(
        "VWRA",
        "VWRA.L",
        "IE00BK5BQT80",
        "Vanguard FTSE All-World UCITS ETF (Acc)",
        AssetClass.ETF,
        "USD",
        "129",
        "156",
        "0.008",
    ),
    SeedAsset(
        "VWCE",
        "VWCE.DE",
        "IE00BK5BQT80",
        "Vanguard FTSE All-World UCITS ETF (Acc)",
        AssetClass.ETF,
        "EUR",
        "119",
        "141",
        "0.008",
    ),
    SeedAsset(
        "EUNL",
        "EUNL.DE",
        "IE00B4L5Y983",
        "iShares Core MSCI World UCITS ETF",
        AssetClass.ETF,
        "EUR",
        "96",
        "112",
        "0.008",
    ),
    SeedAsset(
        "SXR8",
        "SXR8.DE",
        "IE00B5BMR087",
        "iShares Core S&P 500 UCITS ETF",
        AssetClass.ETF,
        "EUR",
        "545",
        "632",
        "0.009",
    ),
    SeedAsset(
        "IWDA",
        "IWDA.AS",
        "IE00B4L5Y983",
        "iShares Core MSCI World UCITS ETF",
        AssetClass.ETF,
        "EUR",
        "96",
        "112",
        "0.008",
    ),
    SeedAsset("ASML", "ASML.AS", "NL0010273215", "ASML Holding NV", AssetClass.STOCK, "EUR", "690", "735", "0.02"),
    SeedAsset("NVDA", "NVDA", "US67066G1040", "NVIDIA Corp.", AssetClass.STOCK, "USD", "128", "188", "0.025"),
    SeedAsset("OTP", "OTP.BD", "HU0000061726", "OTP Bank Nyrt.", AssetClass.STOCK, "HUF", "18600", "29400", "0.014"),
    SeedAsset("MOL", "MOL.BD", "HU0000153937", "MOL Nyrt.", AssetClass.STOCK, "HUF", "2860", "3040", "0.012"),
    SeedAsset(
        "RICHTER",
        "RICHTER.BD",
        "HU0000123096",
        "Richter Gedeon Nyrt.",
        AssetClass.STOCK,
        "HUF",
        "9650",
        "10450",
        "0.011",
    ),
    SeedAsset(
        "MTELEKOM",
        "MTELEKOM.BD",
        "HU0000073507",
        "Magyar Telekom Nyrt.",
        AssetClass.STOCK,
        "HUF",
        "790",
        "1240",
        "0.012",
    ),
)
# 1 USD = x, at the start and end of the synthetic window.
SEED_FX: dict[str, tuple[str, str, str]] = {
    "CHF": ("0.865", "0.795", "0.004"),
    "EUR": ("0.915", "0.858", "0.004"),
    "HUF": ("362", "331", "0.005"),
}


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += dt.timedelta(days=1)
    return days


def synthetic_series(
    key: str, days: list[dt.date], start: str, end: str, daily_vol: str, quantum: Decimal
) -> dict[dt.date, Decimal]:
    """Deterministic geometric random walk pinned to `start` and `end` (a Brownian bridge), all Decimal."""
    rng = random.Random(zlib.crc32(key.encode()))
    scale = Decimal(daily_vol) * SQRT3  # uniform noise with std = daily_vol
    walk = [Decimal(0)]
    for _ in range(len(days) - 1):
        walk.append(walk[-1] + scale * Decimal(rng.randint(-1_000_000, 1_000_000)) / Decimal(1_000_000))
    log_start, log_end = Decimal(start).ln(), Decimal(end).ln()
    last = Decimal(max(len(days) - 1, 1))
    series: dict[dt.date, Decimal] = {}
    for index, day in enumerate(days):
        t = Decimal(index) / last
        log_price = log_start + (log_end - log_start) * t + walk[index] - walk[-1] * t
        series[day] = log_price.exp().quantize(quantum)
    return series


class DemoPortfolio:
    def __init__(self, session: Session, user: User, today: dt.date) -> None:
        self.session = session
        self.user = user
        self.today = today
        self.start = today - dt.timedelta(days=HISTORY_DAYS)
        self.days = _weekdays(self.start - dt.timedelta(days=10), today)
        self.prices: dict[str, dict[dt.date, Decimal]] = {}
        self.fx: dict[str, dict[dt.date, Decimal]] = {}

    # ------------------------------------------------------------- market data

    def seed_market_data(self) -> None:
        for spec in SEED_ASSETS:
            asset = self.session.scalar(
                select(Asset).where(Asset.symbol == spec.symbol, Asset.currency == spec.currency)
            )
            if asset is None:
                asset = Asset(
                    symbol=spec.symbol,
                    isin=spec.isin,
                    name=spec.name,
                    asset_class=spec.asset_class,
                    currency=spec.currency,
                    yf_ticker=spec.yf_ticker,
                )
                self.session.add(asset)
                self.session.flush()
            series = synthetic_series(
                spec.yf_ticker, self.days, spec.start_price, spec.end_price, spec.daily_vol, PRICE_QUANTUM
            )
            self.prices[spec.symbol] = series
            if self.session.scalar(select(AssetPrice.id).where(AssetPrice.asset_id == asset.id).limit(1)) is None:
                self.session.add_all(
                    AssetPrice(asset_id=asset.id, price_date=day, close=close, source=PriceSource.SEED)
                    for day, close in series.items()
                )
        for currency, (start, end, vol) in SEED_FX.items():
            series = synthetic_series(f"USD{currency}", self.days, start, end, vol, FX_QUANTUM)
            self.fx[currency] = series
            exists = self.session.scalar(
                select(FxRate.id).where(FxRate.base == "USD", FxRate.quote == currency).limit(1)
            )
            if exists is None:
                self.session.add_all(
                    FxRate(base="USD", quote=currency, rate_date=day, rate=rate, source=PriceSource.SEED)
                    for day, rate in series.items()
                )
        self.session.flush()

    def day(self, offset: int) -> dt.date:
        """Trading day `offset` calendar days after the start of history (rolled forward off weekends)."""
        day = self.start + dt.timedelta(days=offset)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        return min(day, self.today)

    def price(self, symbol: str, day: dt.date) -> Decimal:
        series = self.prices[symbol]
        while day not in series:
            day -= dt.timedelta(days=1)
        return series[day]

    def usd_rate(self, currency: str, day: dt.date) -> Decimal:
        if currency == "USD":
            return Decimal(1)
        series = self.fx[currency]
        while day not in series:
            day -= dt.timedelta(days=1)
        return series[day]

    def convert(self, amount: Decimal, source: str, target: str, day: dt.date) -> Decimal:
        return (amount * self.usd_rate(target, day) / self.usd_rate(source, day)).quantize(PRICE_QUANTUM)

    def yearly(self, month: int, day: int) -> list[dt.date]:
        dates = []
        for year in range(self.start.year, self.today.year + 1):
            candidate = dt.date(year, month, day)
            while candidate.weekday() >= 5:
                candidate += dt.timedelta(days=1)
            if self.start + dt.timedelta(days=20) < candidate <= self.today:
                dates.append(candidate)
        return dates

    # ------------------------------------------------------------- accounts

    def _account(self, **fields: object) -> Account:
        account = Account(user_id=self.user.id, **fields)
        self.session.add(account)
        self.session.flush()
        return account

    def build(self) -> None:
        self.seed_market_data()
        accounts: list[tuple[Account, Callable[[], list[StandardTransaction]]]] = [
            (
                self._account(
                    name="IBKR Swiss",
                    broker="Interactive Brokers",
                    account_type=AccountType.STANDARD,
                    currency="CHF",
                    external_account_id="U0000001",
                ),
                self.ibkr_swiss,
            ),
            (
                self._account(
                    name="IBKR TBSZ 2025",
                    broker="Interactive Brokers",
                    account_type=AccountType.TBSZ,
                    tbsz_year=2025,
                    currency="EUR",
                    external_account_id="U0000002",
                ),
                self.ibkr_tbsz,
            ),
            (self._account(name="Lightyear", broker="Lightyear", currency="EUR"), self.lightyear),
            (self._account(name="Erste NetBroker", broker="Erste Bank", currency="HUF"), self.erste),
        ]
        for account, build_transactions in accounts:
            transactions = [t for t in build_transactions() if t.date <= self.today]
            ingest_transactions(
                self.session,
                user_id=self.user.id,
                account_id=account.id,
                transactions=transactions,
                source=ImportSource.SEED,
                parser_key="demo_seed",
                message="Demo portfolio generated on first start",
            )

    def _buy(self, symbol: str, currency: str, day: dt.date, quantity: Decimal | int, fee: str) -> StandardTransaction:
        spec = next(s for s in SEED_ASSETS if s.symbol == symbol and s.currency == currency)
        return StandardTransaction(
            date=day,
            type=TransactionType.BUY,
            symbol=symbol,
            isin=spec.isin,
            name=spec.name,
            asset_class=spec.asset_class,
            quantity=Decimal(quantity),
            unit_price=self.price(symbol, day),
            fee=Decimal(fee),
            currency=currency,
        )

    def _sell(self, symbol: str, currency: str, day: dt.date, quantity: int, fee: str) -> StandardTransaction:
        spec = next(s for s in SEED_ASSETS if s.symbol == symbol and s.currency == currency)
        return StandardTransaction(
            date=day,
            type=TransactionType.SELL,
            symbol=symbol,
            isin=spec.isin,
            name=spec.name,
            quantity=Decimal(quantity),
            unit_price=self.price(symbol, day),
            fee=Decimal(fee),
            currency=currency,
        )

    @staticmethod
    def _cash(
        tx_type: TransactionType, day: dt.date, amount: Decimal | str, currency: str, note: str
    ) -> StandardTransaction:
        return StandardTransaction(date=day, type=tx_type, amount=Decimal(amount), currency=currency, description=note)

    def _dividends(
        self, symbol: str, currency: str, month: int, per_share: str, wht: str, shares: Callable[[dt.date], Decimal]
    ) -> list[StandardTransaction]:
        spec = next(s for s in SEED_ASSETS if s.symbol == symbol and s.currency == currency)
        result = []
        for day in self.yearly(month, 15):
            held = shares(day)
            if held <= 0:
                continue
            gross = (held * Decimal(per_share)).quantize(PRICE_QUANTUM)
            result.append(
                StandardTransaction(
                    date=day,
                    type=TransactionType.DIVIDEND,
                    symbol=symbol,
                    isin=spec.isin,
                    amount=gross,
                    tax=(gross * Decimal(wht)).quantize(PRICE_QUANTUM),
                    currency=currency,
                    description=f"{symbol} cash dividend {currency} {per_share} per share",
                )
            )
        return result

    def _fx_pair(self, day: dt.date, sell: str, buy: str, amount: Decimal, fee: str = "0") -> list[StandardTransaction]:
        received = self.convert(amount, sell, buy, day)
        legs = [
            self._cash(TransactionType.FX_CONVERSION, day, -amount, sell, f"FX {sell}→{buy}"),
            self._cash(TransactionType.FX_CONVERSION, day, received, buy, f"FX {sell}→{buy}"),
        ]
        if Decimal(fee):
            legs.append(self._cash(TransactionType.FEE, day, fee, sell, "FX conversion fee"))
        return legs

    def ibkr_swiss(self) -> list[StandardTransaction]:
        tx: list[StandardTransaction] = [
            self._cash(TransactionType.DEPOSIT, self.day(0), "60000", "CHF", "Initial funding")
        ]
        tx += self._fx_pair(self.day(3), "CHF", "USD", Decimal("18000"), fee="2")
        tx += [
            self._buy("NESN", "CHF", self.day(5), 150, "5"),
            self._buy("NOVN", "CHF", self.day(5), 120, "5"),
            self._buy("CHSPI", "CHF", self.day(5), 110, "5"),
            self._buy("AAPL", "USD", self.day(6), 28, "1"),
            self._buy("MSFT", "USD", self.day(6), 14, "1"),
            self._buy("VWRA", "USD", self.day(6), 40, "1"),
        ]
        chspi_buys: list[tuple[dt.date, Decimal]] = [(self.day(5), Decimal(110))]
        for offset in range(60, HISTORY_DAYS, 60):
            day = self.day(offset)
            tx.append(self._cash(TransactionType.DEPOSIT, day, "2500", "CHF", "Monthly savings"))
            quantity = (Decimal(2400) / self.price("CHSPI", day)).to_integral_value(rounding=ROUND_DOWN)
            tx.append(self._buy("CHSPI", "CHF", day, quantity, "5"))
            chspi_buys.append((day, quantity))
        novn_sale = self.day(400)
        tx.append(self._sell("NOVN", "CHF", novn_sale, 40, "5"))

        def novn(day: dt.date) -> Decimal:
            return Decimal(120 if day < novn_sale else 80)

        tx += self._dividends("NESN", "CHF", 4, "3.05", "0.35", lambda _d: Decimal(150))
        tx += self._dividends("NOVN", "CHF", 3, "3.50", "0.35", novn)
        for month in (2, 5, 8, 11):
            tx += self._dividends("AAPL", "USD", month, "0.26", "0.15", lambda _d: Decimal(28))
        for month in (3, 6, 9, 12):
            tx += self._dividends("MSFT", "USD", month, "0.83", "0.15", lambda _d: Decimal(14))
        for day in self.yearly(1, 3) + self.yearly(7, 3):
            tx.append(self._cash(TransactionType.INTEREST, day, "18.40", "CHF", "Credit interest"))
        tx.append(self._cash(TransactionType.FEE, self.day(200), "10", "CHF", "Market data subscription"))
        return tx

    def ibkr_tbsz(self) -> list[StandardTransaction]:
        # TBSZ 2025: deposits are only allowed during the 2025 collection year.
        tx: list[StandardTransaction] = []
        plan = [
            (dt.date(2025, 2, 10), "12000", (40, 30, 6)),
            (dt.date(2025, 6, 10), "6000", (20, 15, 3)),
            (dt.date(2025, 11, 12), "4000", (14, 10, 2)),
        ]
        for deposit_day, amount, (vwce, eunl, sxr8) in plan:
            if not self.start <= deposit_day <= self.today:
                continue
            tx.append(self._cash(TransactionType.DEPOSIT, deposit_day, amount, "EUR", "TBSZ 2025 deposit"))
            buy_day = deposit_day + dt.timedelta(days=2)
            tx += [
                self._buy("VWCE", "EUR", buy_day, vwce, "3"),
                self._buy("EUNL", "EUR", buy_day, eunl, "3"),
                self._buy("SXR8", "EUR", buy_day, sxr8, "3"),
            ]
        return tx

    def lightyear(self) -> list[StandardTransaction]:
        tx: list[StandardTransaction] = [
            self._cash(TransactionType.DEPOSIT, self.day(28), "3000", "EUR", "Top-up"),
            self._buy("ASML", "EUR", self.day(30), 3, "1"),
        ]
        tx += self._fx_pair(self.day(44), "EUR", "USD", Decimal("2000"), fee="7")
        nvda_day = self.day(45)
        usd = self.convert(Decimal(2000), "EUR", "USD", self.day(44))
        nvda_qty = ((usd - 1) / self.price("NVDA", nvda_day)).to_integral_value(rounding=ROUND_DOWN)
        tx.append(self._buy("NVDA", "USD", nvda_day, nvda_qty, "1"))
        for month_index in range(1, 24):
            deposit_day = self.day(20 + month_index * 30)
            tx.append(self._cash(TransactionType.DEPOSIT, deposit_day, "500", "EUR", "Monthly savings plan"))
            quantity = (Decimal(480) / self.price("IWDA", deposit_day)).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
            tx.append(self._buy("IWDA", "EUR", deposit_day, quantity, "0"))
            interest = Decimal("0.9") + Decimal(month_index) * Decimal("0.11")
            tx.append(
                self._cash(
                    TransactionType.INTEREST, self.day(18 + month_index * 30), interest, "EUR", "Interest on cash"
                )
            )
        for month in (3, 6, 9, 12):
            tx += self._dividends("NVDA", "USD", month, "0.01", "0.15", lambda _d: nvda_qty)
        return tx

    def erste(self) -> list[StandardTransaction]:
        tx: list[StandardTransaction] = [
            self._cash(TransactionType.DEPOSIT, self.day(10), "4000000", "HUF", "Befizetés"),
        ]
        first_buys = {"OTP": 60, "MOL": 400, "RICHTER": 80, "MTELEKOM": 1000}
        for symbol, quantity in first_buys.items():
            value = self.price(symbol, self.day(12)) * quantity
            tx.append(
                self._buy(
                    symbol,
                    "HUF",
                    self.day(12),
                    quantity,
                    str(max(Decimal(1900), (value * Decimal("0.0035")).quantize(Decimal(1)))),
                )
            )
        tx.append(self._cash(TransactionType.DEPOSIT, self.day(300), "1000000", "HUF", "Befizetés"))
        tx.append(self._buy("OTP", "HUF", self.day(302), 20, "1900"))
        tx.append(self._buy("MTELEKOM", "HUF", self.day(302), 500, "1900"))
        mol_sale = self.day(500)
        tx.append(self._sell("MOL", "HUF", mol_sale, 100, "1900"))
        otp_top_up = self.day(302)
        tx += self._dividends("OTP", "HUF", 6, "600", "0.15", lambda d: Decimal(80 if d >= otp_top_up else 60))
        tx += self._dividends("MOL", "HUF", 7, "275", "0.15", lambda d: Decimal(300 if d >= mol_sale else 400))
        tx += self._dividends("RICHTER", "HUF", 6, "250", "0.15", lambda _d: Decimal(80))
        tx += self._dividends("MTELEKOM", "HUF", 5, "50", "0.15", lambda d: Decimal(1500 if d >= otp_top_up else 1000))
        return tx


def open_for_demo(session: Session) -> None:
    """A public demo has nobody to claim it, so claim it here with a password nobody will ever hold.

    Sessions only resolve for an account that has one, and first-run setup only waits while no admin does.
    Visitors come in through `/api/auth/demo` instead, which needs no credentials.
    """
    owner = session.scalar(select(User).where(User.is_admin.is_(True), User.password_hash.is_(None)).order_by(User.id))
    if owner is None:
        return
    owner.password_hash = passwords.hash_password(new_token())
    session.commit()
    logger.warning("Demo mode: %s is open to anyone who opens the app. Keep real data off this instance.", owner.email)


def seed(session: Session, settings: Settings) -> None:
    user = ensure_owner(session, settings)
    if settings.demo_mode:
        open_for_demo(session)
    if user is None or not settings.seed_demo_data:
        return
    if session.scalar(select(Account.id).where(Account.user_id == user.id).limit(1)) is not None:
        return
    logger.info("Seeding demo portfolio for %s", user.email)
    DemoPortfolio(session, user, dt.date.today()).build()
    session.commit()
