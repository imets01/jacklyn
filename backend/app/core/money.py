"""Decimal-only money helpers.

Rule: monetary values, quantities and prices are *never* floats. Everything that
enters the domain goes through :func:`to_decimal` or :func:`parse_decimal`,
which reject floats outright so precision bugs fail loudly instead of silently.
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal("0.01")
BASIS = Decimal("0.0001")
ZERO = Decimal("0")
HUNDRED = Decimal("100")

# Currencies with no minor unit in everyday display.
_ZERO_DECIMAL_CURRENCIES = frozenset({"HUF", "JPY", "KRW"})


class FloatNotAllowedError(TypeError):
    """Raised when a float sneaks into a monetary code path."""


def to_decimal(value: object) -> Decimal:
    """Coerce ``value`` to :class:`Decimal`, refusing floats."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("Booleans are not monetary values")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise FloatNotAllowedError(
            f"Float {value!r} passed where a Decimal is required; use str or Decimal"
        )
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"Not a decimal number: {value!r}") from exc
    raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")


# Currency codes/symbols and grouping characters brokers sprinkle into numbers.
_CURRENCY_NOISE = re.compile(r"\b[A-Z]{3}\b|[€$£₣\s\u00a0\u202f']")


def parse_decimal(
    text: str,
    decimal_separator: str = ".",
    thousands_separator: str | None = None,
) -> Decimal | None:
    """Parse a human/broker formatted number.

    Handles ``1,234.56``, ``1 234,56``, ``(12.50)`` accounting negatives, the
    unicode minus sign, trailing minus (``12.50-``) and stray currency codes.
    Returns ``None`` for blank cells.
    """
    raw = text.strip()
    if raw in {"", "-", "--", "n/a", "N/A"}:
        return None

    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative, raw = True, raw[1:-1]
    raw = raw.replace("−", "-")
    if raw.endswith("-"):
        negative, raw = True, raw[:-1]

    raw = _CURRENCY_NOISE.sub("", raw)
    if thousands_separator:
        raw = raw.replace(thousands_separator, "")
    if decimal_separator != ".":
        raw = raw.replace(".", "") if thousands_separator is None else raw
        raw = raw.replace(decimal_separator, ".")
    else:
        # Default: commas are thousands separators.
        raw = raw.replace(",", "")
    raw = raw.rstrip("%")

    if raw.startswith("+"):
        raw = raw[1:]
    if raw.startswith("-"):
        negative, raw = not negative, raw[1:]
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Not a number: {text!r}") from exc
    return -value if negative else value


def quantize_money(value: Decimal, currency: str | None = None) -> Decimal:
    """Round to the currency's display precision (banker's rounding)."""
    exp = Decimal("1") if currency in _ZERO_DECIMAL_CURRENCIES else CENT
    return value.quantize(exp, rounding=ROUND_HALF_EVEN)


def safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """``numerator / denominator`` rounded to 4dp, or 0 when the denominator is 0."""
    if denominator == ZERO:
        return ZERO
    return (numerator / denominator).quantize(BASIS, rounding=ROUND_HALF_EVEN)
