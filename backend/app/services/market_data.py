"""Live prices and FX via yfinance, cached in the asset_prices / fx_rates tables.

Valuation always reads from the database, so the app works offline (seed or last known prices)
and Yahoo is hit at most once per TTL. Refreshes run on a background thread.
"""

import datetime as dt
import logging
import math
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypedDict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.enums import PriceSource
from app.models import Account, Asset, AssetPrice, FxRate, Transaction, User

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


def _download_closes(tickers: list[str], start: dt.date) -> dict[str, dict[dt.date, Any]]:
    """{ticker: {date: close}} using one batched yfinance request."""
    import yfinance as yf  # noqa: PLC0415 - lazy: pulls in pandas, keeps API startup fast

    # Keep yfinance's cache on the data volume so the container filesystem can stay read-only.
    cache_dir = get_settings().data_dir / "yf-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))

    frame = yf.download(
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
        rows = session.execute(
            select(Asset, func.min(Transaction.trade_date))
            .join(Transaction, Transaction.asset_id == Asset.id)
            .where(Asset.yf_ticker.is_not(None))
            .group_by(Asset.id)
        ).all()
        if not rows:
            return
        plans: dict[str, tuple[Asset, dt.date]] = {}
        for asset, first_trade in rows:
            start = self._asset_start(session, asset, first_trade)
            if asset.yf_ticker:
                plans[asset.yf_ticker] = (asset, start)
        for start, tickers in _group_by_start({t: s for t, (_, s) in plans.items()}).items():
            try:
                closes = _download_closes(tickers, start)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"prices: {exc}")
                continue
            for ticker, series in closes.items():
                asset = plans[ticker][0]
                points = {d: p for d, raw in series.items() if (p := _to_decimal(raw, PRICE_QUANTUM)) is not None}
                if points:
                    report.rows_written += _upsert_prices(session, asset.id, points)
                    report.assets_updated += 1

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
