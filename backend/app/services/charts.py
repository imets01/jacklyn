"""Price charts for one asset: intraday to max history from Yahoo, with a short in-memory cache.

Charts are fetched on demand rather than stored: the asset_prices table keeps daily closes from the
first trade only, while a chart may reach back decades or down to five-minute bars.
"""

import datetime as dt
import logging
import threading
import time
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssetPrice
from app.schemas.portfolio import ChartPoint, ChartRange
from app.services.market_data import PRICE_QUANTUM, _to_decimal, load_yfinance

logger = logging.getLogger(__name__)
MAX_POINTS = 800

# range -> (Yahoo period, bar interval)
YAHOO_PERIODS: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "30m"),
    "1M": ("1mo", "1d"),
    "6M": ("6mo", "1d"),
    "YTD": ("ytd", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
    "MAX": ("max", "1wk"),
}
INTRADAY: frozenset[str] = frozenset({"1D", "1W"})
CACHE_SECONDS = {"1D": 120, "1W": 600}
DEFAULT_CACHE_SECONDS = 3600


class ChartCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[float, list[ChartPoint]]] = {}
        self._lock = threading.Lock()

    def get(self, ticker: str, range_key: str) -> list[ChartPoint] | None:
        with self._lock:
            entry = self._entries.get((ticker, range_key))
        if entry is None or entry[0] < time.monotonic():
            return None
        return entry[1]

    def put(self, ticker: str, range_key: str, points: list[ChartPoint]) -> None:
        ttl = CACHE_SECONDS.get(range_key, DEFAULT_CACHE_SECONDS)
        with self._lock:
            self._entries[(ticker, range_key)] = (time.monotonic() + ttl, points)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


chart_cache = ChartCache()


def _downsample(points: list[ChartPoint]) -> list[ChartPoint]:
    if len(points) <= MAX_POINTS:
        return points
    step = len(points) / MAX_POINTS
    sampled = [points[int(i * step)] for i in range(MAX_POINTS)]
    if sampled[-1] is not points[-1]:
        sampled[-1] = points[-1]
    return sampled


def _history(ticker: str, range_key: ChartRange) -> Any:
    period, interval = YAHOO_PERIODS[range_key]
    return load_yfinance().Ticker(ticker).history(period=period, interval=interval, auto_adjust=False, timeout=15)


def yahoo_chart(ticker: str, range_key: ChartRange) -> list[ChartPoint]:
    """Closes from Yahoo; raises on provider errors, returns [] when Yahoo has no data."""
    if (cached := chart_cache.get(ticker, range_key)) is not None:
        return cached
    frame = _history(ticker, range_key)
    points: list[ChartPoint] = []
    if frame is not None and not frame.empty and "Close" in frame:
        for index, raw in frame["Close"].dropna().items():
            close = _to_decimal(raw, PRICE_QUANTUM)
            if close is None:
                continue
            moment = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt.UTC)
            points.append(ChartPoint(time=moment, close=close))
    points = _downsample(points)
    chart_cache.put(ticker, range_key, points)
    return points


def range_start(range_key: ChartRange, today: dt.date) -> dt.date | None:
    match range_key:
        case "1D":
            return today - dt.timedelta(days=4)  # the last couple of closes, across a weekend
        case "1W":
            return today - dt.timedelta(days=7)
        case "1M":
            return today - dt.timedelta(days=31)
        case "6M":
            return today - dt.timedelta(days=183)
        case "YTD":
            return dt.date(today.year, 1, 1)
        case "1Y":
            return today - dt.timedelta(days=365)
        case "5Y":
            return today - dt.timedelta(days=5 * 365 + 1)
        case "MAX":
            return None


def stored_chart(session: Session, asset_id: int, range_key: ChartRange, today: dt.date) -> list[ChartPoint]:
    """Daily closes we already have (live history since the first trade, or seed data)."""
    query = select(AssetPrice.price_date, AssetPrice.close).where(AssetPrice.asset_id == asset_id)
    if (start := range_start(range_key, today)) is not None:
        query = query.where(AssetPrice.price_date >= start)
    rows = session.execute(query.order_by(AssetPrice.price_date)).all()
    return _downsample(
        [ChartPoint(time=dt.datetime.combine(day, dt.time(), tzinfo=dt.UTC), close=close) for day, close in rows]
    )


def change(points: list[ChartPoint]) -> tuple[Decimal | None, Decimal | None]:
    if len(points) < 2:
        return None, None
    first, last = points[0].close, points[-1].close
    delta = last - first
    return delta, (delta / first).quantize(Decimal("0.0001")) if first else None
