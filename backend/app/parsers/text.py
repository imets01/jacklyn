"""Locale-tolerant parsing of numbers and dates found in broker exports."""

import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Literal

DecimalSeparator = Literal[".", ","]

# Spaces (incl. NBSP / narrow NBSP / thin space) and apostrophes (Swiss 1'234.50) are always grouping.
_GROUPING_CHARS = re.compile(r"[\s   '’]")
_EDGE_NOISE = re.compile(r"^[A-Za-z€$£¥₣₽₹]+\.?|[A-Za-z€$£¥₣₽₹%]+\.?$")
_CANONICAL = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")
_PLAIN_DIGITS = re.compile(r"^\d+$")


class NumberFormatError(ValueError):
    pass


def _strip_noise(raw: str) -> tuple[str, bool]:
    text = raw.strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    text = _GROUPING_CHARS.sub("", text)
    # "USD-12.50", "-$12.50", "-12.50 EUR", "12.50€", "12.50-": peel currency noise and signs off the edges.
    previous = None
    while previous != text:
        previous = text
        text = _EDGE_NOISE.sub("", text)
        if text.startswith("+"):
            text = text[1:]
        elif text.startswith("-"):
            negative, text = not negative, text[1:]
        elif text.endswith("-"):
            negative, text = not negative, text[:-1]
    return text, negative


def _infer_separator(text: str) -> DecimalSeparator:
    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        return "," if text.rfind(",") > text.rfind(".") else "."
    if has_comma:
        head, _, tail = text.rpartition(",")
        # "1,234" or "12,345,678" read as thousands; "12,5" or "0,123" as a decimal comma.
        if text.count(",") > 1 or (len(tail) == 3 and _PLAIN_DIGITS.match(head) and head != "0"):
            return "."
        return ","
    if text.count(".") > 1:
        return ","
    return "."


def parse_decimal(raw: str | None, decimal_separator: DecimalSeparator | None = None) -> Decimal | None:
    """Parse '1.234,56', '1,234.56', "1'234.56", '(12.5)', '12.50 EUR', '1 234,56', '1.5E-3'."""
    if raw is None:
        return None
    if not raw.strip() or raw.strip() in {"-", "--", "n/a", "N/A"}:
        return None
    text, negative = _strip_noise(raw)
    if not text:
        raise NumberFormatError(f"'{raw}' is not a number")
    if _CANONICAL.match(text) and decimal_separator != ",":
        canonical = text
    else:
        separator = decimal_separator or _infer_separator(text)
        grouping = "." if separator == "," else ","
        canonical = text.replace(grouping, "").replace(separator, ".")
        if not _CANONICAL.match(canonical):
            raise NumberFormatError(f"'{raw}' is not a number")
    try:
        value = Decimal(canonical)
    except InvalidOperation as exc:  # pragma: no cover - regex guards this
        raise NumberFormatError(f"'{raw}' is not a number") from exc
    return -value if negative else value


def detect_decimal_separator(values: Iterable[str]) -> DecimalSeparator:
    """Vote across a column (or a whole sheet) of numeric-looking strings."""
    votes: Counter[str] = Counter()
    for raw in values:
        text, _ = _strip_noise(raw)
        if not text or not re.fullmatch(r"[\d.,]+", text) or not re.search(r"\d", text):
            continue
        has_comma, has_dot = "," in text, "." in text
        if has_comma and has_dot:
            votes["," if text.rfind(",") > text.rfind(".") else "."] += 3
        elif has_comma:
            tail = text.rpartition(",")[2]
            votes["," if len(tail) != 3 or (text.count(",") == 1 and text.startswith("0,")) else "."] += 1
        elif has_dot:
            tail = text.rpartition(".")[2]
            votes["." if len(tail) != 3 or (text.count(".") == 1 and text.startswith("0.")) else ","] += 1
    if not votes:
        return "."
    return "," if votes[","] > votes["."] else "."


# Ordered by preference: for ambiguous values (03/04/2024), day-first wins — the user base is European.
DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d, %H:%M:%S",
    "%Y%m%d",
    "%Y%m%d;%H%M%S",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%y",
    "%Y.%m.%d",
    "%Y.%m.%d.",
    "%Y. %m. %d.",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d. %H:%M:%S",
    "%Y.%m.%d. %H:%M",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M",
    "%d-%m-%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
)
ISO8601 = "ISO8601"


class DateFormatError(ValueError):
    pass


def _parse_iso(text: str) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            return None


def parse_date(raw: str | None, date_format: str | None = None) -> dt.date | None:
    if raw is None or not raw.strip():
        return None
    text = " ".join(raw.strip().split())
    formats: list[str] = []
    if date_format and date_format != ISO8601:
        formats.append(date_format)
    if date_format in (None, ISO8601) or not formats:
        iso = _parse_iso(text)
        if iso:
            return iso
    if date_format is None:
        formats.extend(DATE_FORMATS)
    for fmt in formats:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Spreadsheet cells are normalized to ISO, so accept that even with an explicit format.
    iso = _parse_iso(text)
    if iso:
        return iso
    raise DateFormatError(f"'{raw}' does not match date format {date_format or 'auto'}")


def detect_date_format(values: Iterable[str]) -> str | None:
    samples = [" ".join(v.strip().split()) for v in values if v and v.strip()][:200]
    if not samples:
        return None
    if all(_parse_iso(s) for s in samples):
        return ISO8601
    for fmt in DATE_FORMATS:
        try:
            for sample in samples:
                dt.datetime.strptime(sample, fmt)
        except ValueError:
            continue
        return fmt
    return None


def looks_numeric(raw: str) -> bool:
    try:
        return parse_decimal(raw) is not None
    except NumberFormatError:
        return False


def looks_like_date(raw: str) -> bool:
    try:
        return parse_date(raw) is not None
    except DateFormatError:
        return False
