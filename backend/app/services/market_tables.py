"""In-memory, forward-filled price and FX series loaded once per request."""

import datetime as dt
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssetPrice, FxRate


@dataclass
class Series:
    dates: list[dt.date]
    values: list[Decimal]

    def at(self, on: dt.date) -> tuple[dt.date, Decimal] | None:
        """Last observation on or before `on`; before the first point, the first point (backfill)."""
        if not self.dates:
            return None
        index = bisect_right(self.dates, on) - 1
        index = max(index, 0)
        return self.dates[index], self.values[index]

    def before(self, on: dt.date) -> tuple[dt.date, Decimal] | None:
        index = bisect_right(self.dates, on - dt.timedelta(days=1)) - 1
        if index < 0:
            return None
        return self.dates[index], self.values[index]

    @property
    def last_date(self) -> dt.date | None:
        return self.dates[-1] if self.dates else None


def _build[K](points: Iterable[tuple[K, dt.date, Decimal]]) -> dict[K, Series]:
    grouped: dict[K, dict[dt.date, Decimal]] = defaultdict(dict)
    for key, date, value in points:
        grouped[key][date] = value
    return {
        key: Series(dates=sorted(values), values=[values[d] for d in sorted(values)]) for key, values in grouped.items()
    }


class PriceTable:
    def __init__(self, series: dict[int, Series]) -> None:
        self.series = series
        self.fallback: set[int] = set()  # assets priced only by their own trades

    @classmethod
    def load(cls, session: Session, asset_ids: Iterable[int]) -> "PriceTable":
        ids = list(set(asset_ids))
        if not ids:
            return cls({})
        rows = session.execute(
            select(AssetPrice.asset_id, AssetPrice.price_date, AssetPrice.close).where(AssetPrice.asset_id.in_(ids))
        )
        return cls(_build((int(asset_id), date, close) for asset_id, date, close in rows))

    def add_fallback(self, asset_id: int, date: dt.date, price: Decimal) -> None:
        """Use a trade price where no market data exists (e.g. an unlisted fund)."""
        self.fallback.add(asset_id)
        series = self.series.setdefault(asset_id, Series([], []))
        index = bisect_right(series.dates, date)
        if index and series.dates[index - 1] == date:
            series.values[index - 1] = price
        else:
            series.dates.insert(index, date)
            series.values.insert(index, price)

    def has(self, asset_id: int) -> bool:
        return asset_id in self.series and bool(self.series[asset_id].dates)

    def at(self, asset_id: int, on: dt.date) -> tuple[dt.date, Decimal] | None:
        series = self.series.get(asset_id)
        return series.at(on) if series else None

    def before(self, asset_id: int, on: dt.date) -> tuple[dt.date, Decimal] | None:
        """The previous close. None for trade-priced assets: two trades months apart are not a day's move."""
        series = self.series.get(asset_id)
        return series.before(on) if series and asset_id not in self.fallback else None


class FxTable:
    """USD-based quotes (1 USD = rate X); any cross is triangulated through USD."""

    def __init__(self, series: dict[str, Series]) -> None:
        self.series = series

    @classmethod
    def load(cls, session: Session) -> "FxTable":
        rows = session.execute(select(FxRate.quote, FxRate.rate_date, FxRate.rate).where(FxRate.base == "USD"))
        return cls(_build((str(quote), date, rate) for quote, date, rate in rows))

    def usd_rate(self, currency: str, on: dt.date) -> Decimal | None:
        if currency == "USD":
            return Decimal(1)
        series = self.series.get(currency)
        point = series.at(on) if series else None
        return point[1] if point else None

    def rate(self, from_currency: str, to_currency: str, on: dt.date) -> Decimal | None:
        if from_currency == to_currency:
            return Decimal(1)
        source, target = self.usd_rate(from_currency, on), self.usd_rate(to_currency, on)
        if source is None or target is None or source == 0:
            return None
        return target / source

    def convert(self, amount: Decimal, from_currency: str, to_currency: str, on: dt.date) -> Decimal | None:
        rate = self.rate(from_currency, to_currency, on)
        return None if rate is None else amount * rate

    def known(self, currency: str) -> bool:
        return currency == "USD" or currency in self.series

    @property
    def last_date(self) -> dt.date | None:
        dates = [series.last_date for series in self.series.values() if series.last_date]
        return max(dates) if dates else None
