"""Hungarian TBSZ (tartós befektetési számla) lifecycle.

* Collection year (``tbsz_year``): deposits allowed only during this calendar year.
* Lock-up: the 5 calendar years after the collection year.
  - Withdraw after the 3rd year: 10% tax on gains.
  - Hold through the 5th year (Dec 31 of ``tbsz_year + 5``): gains are tax-free.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class TbszPhase(StrEnum):
    COLLECTING = "collecting"
    LOCKED = "locked"
    REDUCED_TAX = "reduced_tax"
    MATURED = "matured"


@dataclass(frozen=True, slots=True)
class TbszStatus:
    year: int
    phase: TbszPhase
    reduced_tax_date: date
    maturity_date: date
    days_to_maturity: int
    progress: float  # 0..1 of the lock-up elapsed — a UI ratio, not money


def tbsz_status(tbsz_year: int, today: date | None = None) -> TbszStatus:
    today = today or date.today()
    start = date(tbsz_year, 1, 1)
    reduced = date(tbsz_year + 3, 12, 31)
    maturity = date(tbsz_year + 5, 12, 31)

    if today.year <= tbsz_year:
        phase = TbszPhase.COLLECTING
    elif today <= reduced:
        phase = TbszPhase.LOCKED
    elif today <= maturity:
        phase = TbszPhase.REDUCED_TAX
    else:
        phase = TbszPhase.MATURED

    total_days = (maturity - start).days
    elapsed = min(max((today - start).days, 0), total_days)
    return TbszStatus(
        year=tbsz_year,
        phase=phase,
        reduced_tax_date=reduced,
        maturity_date=maturity,
        days_to_maturity=max((maturity - today).days, 0),
        progress=round(elapsed / total_days, 4),
    )
