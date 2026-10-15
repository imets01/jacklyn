"""Currency conversion.

Phase 1 ships a static, Decimal-exact rate table so the app works offline.
Swap :data:`STATIC_RATES_PER_EUR` for an ECB/provider feed later; callers only
depend on :class:`FxConverter`.
"""

from decimal import Decimal

from app.core.money import to_decimal

BASE_CURRENCIES = ("CHF", "EUR", "HUF", "USD")

# Units of currency per 1 EUR (indicative mid rates, Oct 2026 placeholder).
STATIC_RATES_PER_EUR: dict[str, Decimal] = {
    "EUR": Decimal("1"),
    "CHF": Decimal("0.9350"),
    "USD": Decimal("1.0900"),
    "HUF": Decimal("395.00"),
    "GBP": Decimal("0.8450"),
}


class UnsupportedCurrencyError(ValueError):
    pass


class FxConverter:
    def __init__(self, rates_per_eur: dict[str, Decimal] | None = None) -> None:
        self._rates = {k: to_decimal(v) for k, v in (rates_per_eur or STATIC_RATES_PER_EUR).items()}

    @property
    def currencies(self) -> list[str]:
        return sorted(self._rates)

    def supports(self, currency: str) -> bool:
        return currency in self._rates

    def rate(self, from_ccy: str, to_ccy: str) -> Decimal:
        """How many ``to_ccy`` one unit of ``from_ccy`` buys."""
        if from_ccy == to_ccy:
            return Decimal("1")
        try:
            return self._rates[to_ccy] / self._rates[from_ccy]
        except KeyError as exc:
            raise UnsupportedCurrencyError(f"No FX rate for {exc.args[0]}") from exc

    def convert(self, amount: Decimal, from_ccy: str, to_ccy: str) -> Decimal:
        return to_decimal(amount) * self.rate(from_ccy, to_ccy)

    def table(self, base: str) -> dict[str, Decimal]:
        """Value of one unit of each currency in ``base``."""
        return {ccy: self.rate(ccy, base) for ccy in self.currencies}


default_fx = FxConverter()
