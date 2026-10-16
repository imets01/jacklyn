from decimal import Decimal
from typing import Any, ClassVar

import pytest
import yfinance

from app.services import market_data


class FakeTicker:
    LISTINGS: ClassVar[dict[str, dict[str, Any]]] = {
        "QDVE.DE": {"currency": "EUR", "lastPrice": 46.51},
        "SAME.DE": {"currency": "EUR", "lastPrice": 900.0},  # same symbol, different security
        "SAME.AS": {"currency": "EUR", "lastPrice": 31.0},
        "USDONLY": {"currency": "USD", "lastPrice": 10.0},
    }

    def __init__(self, ticker: str) -> None:
        if ticker not in self.LISTINGS:
            raise KeyError(ticker)
        self.fast_info = self.LISTINGS[ticker]


@pytest.fixture(autouse=True)
def fake_yahoo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)


def test_find_listing_matches_currency_and_plausible_price() -> None:
    assert market_data.find_listing("QDVE", "EUR", Decimal("32.77")) == "QDVE.DE"


def test_find_listing_skips_implausible_prices() -> None:
    assert market_data.find_listing("SAME", "EUR", Decimal("30")) == "SAME.AS"


def test_find_listing_requires_matching_currency() -> None:
    assert market_data.find_listing("USDONLY", "EUR", Decimal("10")) is None
    assert market_data.find_listing("UNKNOWN", "EUR", Decimal("10")) is None
