"""Hungarian TBSZ (tartós befektetési számla) lock-up milestones.

The vintage ("gyűjtőév") is the calendar year deposits are made in. The 5-year lock-up starts on
1 January of the following year: after 3 years the gains tax drops to 10%, after 5 years it is 0%.
"""

import datetime as dt


def reduced_rate_from(vintage_year: int) -> dt.date:
    return dt.date(vintage_year + 4, 1, 1)


def tax_free_from(vintage_year: int) -> dt.date:
    return dt.date(vintage_year + 6, 1, 1)
