"""Deterministic transaction fingerprints for idempotent imports."""

import hashlib
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal

from app.parsers.base import ParsedTransaction


def _dec(value: Decimal | None) -> str:
    # normalize() so 10, 10.0 and 10.00 hash the same
    return "" if value is None else format(value.normalize(), "f")


def _content_key(tx: ParsedTransaction) -> str:
    if tx.external_id:
        # Broker IDs are authoritative, but one broker row can yield several
        # transactions (e.g. both legs of an FX trade), so keep the currency.
        return f"ext|{tx.external_id}|{tx.type.value}|{tx.currency}"
    return "|".join(
        [
            tx.trade_date.isoformat(),
            tx.type.value,
            (tx.isin or tx.symbol or ""),
            _dec(tx.quantity),
            _dec(tx.price),
            _dec(tx.amount),
            tx.currency,
        ]
    )


def fingerprints(transactions: Iterable[ParsedTransaction]) -> list[str]:
    """Fingerprint each transaction.

    Two genuinely identical rows (e.g. two equal buys on the same day) get an
    occurrence counter, so they stay distinct while re-importing the same file
    still produces the same fingerprints.
    """
    seen: Counter[str] = Counter()
    result = []
    for tx in transactions:
        key = _content_key(tx)
        seen[key] += 1
        digest = hashlib.sha256(f"{key}|#{seen[key]}".encode()).hexdigest()
        result.append(digest)
    return result
