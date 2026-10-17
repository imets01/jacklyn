"""Live prices and FX via yfinance, cached in the asset_prices / fx_rates tables.

Valuation always reads from the database, so the app works offline (seed or last known prices)
and Yahoo is hit at most once per TTL. Refreshes run on a background thread.
"""

import datetime as dt
import logging
import math
import threading
from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypedDict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.enums import PriceSource
from app.models import Account, Asset, AssetPrice, AssetProfile, FxRate, Transaction, User
from app.services.asset_info import (
    logo_candidates,
    profile_is_stale,
    refresh_logos,
    refresh_profile,
    resolve_logos,
)
from app.services.assets import us_share_class

logger = logging.getLogger(__name__)
PRICE_QUANTUM = Decimal("0.000001")
FX_QUANTUM = Decimal("0.00000001")
DEFAULT_CURRENCIES = frozenset({"CHF", "EUR", "HUF", "USD"})


class LiveStatus(TypedDict):
    live_enabled: bool
    refreshing: bool
    last_refresh_at: dt.datetime | None
    last_refresh_error: str | None


@dataclass
class RefreshReport:
    assets_updated: int = 0
    fx_pairs_updated: int = 0
    rows_written: int = 0
    profiles_updated: int = 0
    logos_fetched: int = 0
    errors: list[str] = field(default_factory=list)


def _to_decimal(value: Any, quantum: Decimal) -> Decimal | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number <= 0:
        return None
    # repr() is the shortest round-trip form of the float Yahoo sent; quantize from there.
    return Decimal(repr(number)).quantize(quantum)


def load_yfinance() -> Any:
    """Import yfinance lazily (it pulls in pandas) with its cache on the data volume."""
    import yfinance as yf  # noqa: PLC0415 - lazy: keeps API startup fast

    # Keep yfinance's cache on the data volume so the container filesystem can stay read-only.
    cache_dir = get_settings().data_dir / "yf-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))
    return yf


def _download_closes(tickers: list[str], start: dt.date) -> dict[str, dict[dt.date, Any]]:
    """{ticker: {date: close}} using one batched yfinance request."""
    frame = load_yfinance().download(
        tickers,
        start=start.isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
        timeout=20,
        multi_level_index=True,
    )
    closes: dict[str, dict[dt.date, Any]] = {}
    if frame is None or frame.empty:
        return closes
    for ticker in tickers:
        try:
            column = frame[ticker]["Close"]
        except KeyError:
            continue
        closes[ticker] = {
            index.date() if hasattr(index, "date") else index: value for index, value in column.dropna().items()
        }
    return closes


class MarketDataService:
    def __init__(self, session_factory: sessionmaker[Session], settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._lock = threading.Lock()
        self._lookup_attempted: set[int] = set()  # asset ids already probed this process
        self.last_refresh_at: dt.datetime | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.live_market_data

    @property
    def refreshing(self) -> bool:
        return self._lock.locked()

    def is_stale(self) -> bool:
        if self.last_refresh_at is None:
            return True
        age = dt.datetime.now(dt.UTC) - self.last_refresh_at
        return age.total_seconds() > self._settings.market_data_ttl_seconds

    def status(self) -> LiveStatus:
        return {
            "live_enabled": self.enabled,
            "refreshing": self.refreshing,
            "last_refresh_at": self.last_refresh_at,
            "last_refresh_error": self.last_error,
        }

    def refresh_in_background(self, *, force: bool = False) -> bool:
        if not self.enabled or self.refreshing or (not force and not self.is_stale()):
            return False
        threading.Thread(target=self.refresh, name="market-data-refresh", daemon=True).start()
        return True

    def refresh(self) -> RefreshReport:
        report = RefreshReport()
        if not self._lock.acquire(blocking=False):
            report.errors.append("A refresh is already running.")
            return report
        try:
            with self._session_factory() as session:
                self._refresh_assets(session, report)
                self._refresh_fx(session, report)
                session.commit()
                # Profiles and logos are slower and purely cosmetic: prices are already saved.
                self._refresh_profiles(session, report)
                session.commit()
            self.last_error = "; ".join(report.errors) or None
        except Exception as exc:  # noqa: BLE001 - network/provider errors must not crash the API
            logger.warning("Market data refresh failed: %s", exc)
            self.last_error = str(exc)
            report.errors.append(str(exc))
        finally:
            self.last_refresh_at = dt.datetime.now(dt.UTC)
            self._lock.release()
        return report

    # ---------------------------------------------------------------- assets

    def _refresh_assets(self, session: Session, report: RefreshReport) -> None:
        self._resolve_missing_tickers(session)
        silent = self._download_prices(session, report)
        # A ticker that has never returned a quote is most likely wrong (BRK.B where Yahoo wants BRK-B,
        # or a London USD line stored as a bare US symbol), so look for another listing right away.
        # Only when Yahoo answered for other assets: an outage must not send every holding to a lookup.
        if silent and report.assets_updated and (fixed := self._resolve_missing_tickers(session, retry=silent)):
            self._download_prices(session, report, only=fixed)

    def _download_prices(
        self, session: Session, report: RefreshReport, only: Collection[int] | None = None
    ) -> set[int]:
        """Fetch quotes for held assets; returns the ids of those whose ticker has never returned any."""
        query = (
            select(Asset, func.min(Transaction.trade_date))
            .join(Transaction, Transaction.asset_id == Asset.id)
            .where(Asset.yf_ticker.is_not(None))
            .group_by(Asset.id)
        )
        if only is not None:
            query = query.where(Asset.id.in_(only))
        plans: dict[str, tuple[Asset, dt.date]] = {}
        for asset, first_trade in session.execute(query).all():
            start = self._asset_start(session, asset, first_trade)
            if asset.yf_ticker:
                plans[asset.yf_ticker] = (asset, start)
        silent: set[int] = set()
        for start, tickers in _group_by_start({t: s for t, (_, s) in plans.items()}).items():
            try:
                closes = _download_closes(tickers, start)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"prices: {exc}")
                continue
            for ticker in tickers:
                asset = plans[ticker][0]
                series = closes.get(ticker, {})
                points = {d: p for d, raw in series.items() if (p := _to_decimal(raw, PRICE_QUANTUM)) is not None}
                if points:
                    report.rows_written += _upsert_prices(session, asset.id, points)
                    report.assets_updated += 1
                else:
                    silent.add(asset.id)
        if silent:  # a ticker that worked before may just be delisted: keep its history and stop there
            silent -= set(
                session.scalars(
                    select(AssetPrice.asset_id).where(
                        AssetPrice.asset_id.in_(silent), AssetPrice.source == PriceSource.YFINANCE
                    )
                )
            )
        return silent

    def _resolve_missing_tickers(self, session: Session, retry: Collection[int] = ()) -> list[int]:
        """Find a Yahoo listing for held assets that have none, or whose ticker is in `retry`.

        Each asset is looked up at most once per process. Returns the ids whose ticker changed.
        """
        last_trade = (
            select(Transaction.asset_id, func.max(Transaction.trade_date).label("last"))
            .where(Transaction.unit_price.is_not(None))
            .group_by(Transaction.asset_id)
            .subquery()
        )
        rows = session.execute(
            select(Asset, Transaction.unit_price)
            .join(last_trade, last_trade.c.asset_id == Asset.id)
            .join(
                Transaction,
                (Transaction.asset_id == Asset.id) & (Transaction.trade_date == last_trade.c.last),
            )
            .where(Asset.yf_ticker.is_(None) | Asset.id.in_(retry))
        ).all()
        seen: set[int] = set()
        changed: list[int] = []
        for asset, reference_price in rows:
            if asset.id in seen or asset.id in self._lookup_attempted or reference_price is None:
                continue
            seen.add(asset.id)
            self._lookup_attempted.add(asset.id)
            ticker = find_listing(asset.symbol, asset.currency, reference_price, exclude=asset.yf_ticker)
            if ticker:
                logger.info("Matched %s (%s) to Yahoo listing %s", asset.symbol, asset.currency, ticker)
                asset.yf_ticker = ticker
                changed.append(asset.id)
                # The profile was looked up under the old ticker (or none): fetch it again.
                if (profile := session.get(AssetProfile, asset.id)) is not None:
                    session.delete(profile)
        session.flush()
        return changed

    def _refresh_profiles(self, session: Session, report: RefreshReport, *, limit: int = 25) -> None:
        """Fund issuer, TER, sector and the logo key for held assets, then any logos still missing."""
        now = dt.datetime.now(dt.UTC)
        held = session.scalars(
            select(Asset).where(Asset.id.in_(select(Transaction.asset_id).where(Transaction.asset_id.is_not(None))))
        ).all()
        profiles = {p.asset_id: p for p in session.scalars(select(AssetProfile))}
        stale = [asset for asset in held if profile_is_stale(profiles.get(asset.id), now)]
        for asset in stale[:limit]:
            profiles[asset.id] = refresh_profile(
                session, asset, use_network=True, eulerpool_token=self._settings.eulerpool_token
            )
            report.profiles_updated += 1
        session.flush()
        held_by_id = {asset.id: asset for asset in held}
        candidates = {
            asset_id: logo_candidates(held_by_id[asset_id], profile)
            for asset_id, profile in profiles.items()
            if asset_id in held_by_id
        }
        currencies = set(session.scalars(select(Transaction.currency).distinct()))
        try:
            chosen, stored = resolve_logos(session, candidates)
            for asset_id, key in chosen.items():
                profiles[asset_id].logo_key = key
            stored += refresh_logos(session, {f"currency:{code}" for code in currencies})
            report.logos_fetched += stored
        except Exception as exc:  # noqa: BLE001 - logos are optional
            report.errors.append(f"logos: {exc}")

    @staticmethod
    def _asset_start(session: Session, asset: Asset, first_trade: dt.date) -> dt.date:
        last_live = session.scalar(
            select(func.max(AssetPrice.price_date)).where(
                AssetPrice.asset_id == asset.id, AssetPrice.source == PriceSource.YFINANCE
            )
        )
        if last_live is None:
            return first_trade - dt.timedelta(days=7)  # full backfill replaces synthetic history
        return last_live - dt.timedelta(days=5)

    # ---------------------------------------------------------------- fx

    def _refresh_fx(self, session: Session, report: RefreshReport) -> None:
        currencies = set(DEFAULT_CURRENCIES)
        currencies.update(session.scalars(select(Transaction.currency).distinct()))
        currencies.update(session.scalars(select(Asset.currency).distinct()))
        currencies.update(session.scalars(select(Account.currency).distinct()))
        currencies.update(session.scalars(select(User.base_currency).distinct()))
        currencies.discard("USD")
        first_trade = session.scalar(select(func.min(Transaction.trade_date))) or dt.date.today()
        plans: dict[str, tuple[str, dt.date]] = {}
        for currency in sorted(currencies):
            last_live = session.scalar(
                select(func.max(FxRate.rate_date)).where(
                    FxRate.base == "USD", FxRate.quote == currency, FxRate.source == PriceSource.YFINANCE
                )
            )
            start = first_trade - dt.timedelta(days=7) if last_live is None else last_live - dt.timedelta(days=5)
            plans[f"{currency}=X"] = (currency, start)
        for start, tickers in _group_by_start({t: s for t, (_, s) in plans.items()}).items():
            try:
                closes = _download_closes(tickers, start)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"fx: {exc}")
                continue
            for ticker, series in closes.items():
                currency = plans[ticker][0]
                points = {d: r for d, raw in series.items() if (r := _to_decimal(raw, FX_QUANTUM)) is not None}
                if points:
                    report.rows_written += _upsert_fx(session, currency, points)
                    report.fx_pairs_updated += 1


def _group_by_start(starts: dict[str, dt.date]) -> dict[dt.date, list[str]]:
    """Batch tickers into few requests: everything needing a backfill shares the earliest start."""
    if not starts:
        return {}
    recent_cutoff = dt.date.today() - dt.timedelta(days=30)
    recent = [ticker for ticker, start in starts.items() if start >= recent_cutoff]
    backfill = [ticker for ticker, start in starts.items() if start < recent_cutoff]
    groups: dict[dt.date, list[str]] = {}
    if recent:
        groups[min(starts[t] for t in recent)] = recent
    if backfill:
        groups.setdefault(min(starts[t] for t in backfill), []).extend(backfill)
    return groups


def _upsert_prices(session: Session, asset_id: int, points: dict[dt.date, Decimal]) -> int:
    # Real quotes supersede the synthetic demo series entirely.
    session.execute(
        delete(AssetPrice).where(AssetPrice.asset_id == asset_id, AssetPrice.source != PriceSource.YFINANCE)
    )
    existing = {
        row.price_date: row
        for row in session.scalars(
            select(AssetPrice).where(AssetPrice.asset_id == asset_id, AssetPrice.price_date.in_(list(points)))
        )
    }
    now = dt.datetime.now(dt.UTC)
    for date, close in points.items():
        if (row := existing.get(date)) is not None:
            row.close, row.source, row.fetched_at = close, PriceSource.YFINANCE, now
        else:
            session.add(AssetPrice(asset_id=asset_id, price_date=date, close=close, source=PriceSource.YFINANCE))
    return len(points)


def _upsert_fx(session: Session, currency: str, points: dict[dt.date, Decimal]) -> int:
    session.execute(
        delete(FxRate).where(FxRate.base == "USD", FxRate.quote == currency, FxRate.source != PriceSource.YFINANCE)
    )
    existing = {
        row.rate_date: row
        for row in session.scalars(
            select(FxRate).where(FxRate.base == "USD", FxRate.quote == currency, FxRate.rate_date.in_(list(points)))
        )
    }
    now = dt.datetime.now(dt.UTC)
    for date, rate in points.items():
        if (row := existing.get(date)) is not None:
            row.rate, row.source, row.fetched_at = rate, PriceSource.YFINANCE, now
        else:
            session.add(FxRate(base="USD", quote=currency, rate_date=date, rate=rate, source=PriceSource.YFINANCE))
    return len(points)


# Exchanges to try, in order, when an asset's listing is unknown. Yahoo's ISIN search tends to
# return a different-currency listing (e.g. London USD), so we probe by symbol and verify instead.
LISTING_SUFFIXES: dict[str, tuple[str, ...]] = {
    "EUR": (".DE", ".AS", ".PA", ".MI", ".F", ".BR", ".MC", ".VI"),
    "USD": ("", ".L"),  # US listings first, then London's USD lines (e.g. iShares sector ETFs)
    "CHF": (".SW",),
    "GBP": (".L",),
    "HUF": (".BD",),
}


def find_listing(symbol: str, currency: str, reference_price: Decimal, *, exclude: str | None = None) -> str | None:
    """First listing whose currency matches and whose price is plausible versus the last trade price.

    `exclude` is a ticker already known not to work, such as a stored one that never returned quotes.
    """
    yf = load_yfinance()
    if not symbol.replace(".", "").replace("-", "").isalnum() or len(symbol) > 12:
        return None
    if currency == "USD":
        symbol = us_share_class(symbol)
    for suffix in LISTING_SUFFIXES.get(currency, ()):
        ticker = f"{symbol}{suffix}"
        if ticker == exclude:
            continue
        try:
            info = yf.Ticker(ticker).fast_info
            listed_currency = info.get("currency")
            price = info.get("lastPrice")
        except Exception:  # noqa: BLE001 - unknown symbols raise all sorts of errors
            continue
        if listed_currency != currency or not price or math.isnan(price):
            continue
        ratio = Decimal(repr(float(price))) / reference_price
        if Decimal("0.2") <= ratio <= Decimal("5"):  # guards against a same-symbol, different security
            return ticker
    return None
