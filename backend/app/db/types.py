import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Dialect, Numeric, String
from sqlalchemy.types import TypeDecorator, TypeEngine


class DecimalType(TypeDecorator[Decimal]):
    """Exact decimal column that never round-trips through binary floating point.

    PostgreSQL gets a native ``NUMERIC(precision, scale)``. SQLite has no exact
    decimal storage (its NUMERIC affinity silently coerces to REAL), so there the
    value is persisted as its canonical text form and parsed back into ``Decimal``.
    Aggregations therefore happen in Python, never in SQL, on SQLite.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 28, scale: int = 10) -> None:
        super().__init__()
        self.precision = precision
        self.scale = scale

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(64))
        return dialect.type_descriptor(Numeric(self.precision, self.scale, asdecimal=True))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("Refusing to store a float in a decimal column; use Decimal.")
        decimal_value = value if isinstance(value, Decimal) else Decimal(value)
        if dialect.name == "sqlite":
            return format(decimal_value, "f")
        return decimal_value

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))

    def __repr__(self) -> str:
        return f"DecimalType(precision={self.precision}, scale={self.scale})"


class UTCDateTime(TypeDecorator[dt.datetime]):
    """Timezone-aware UTC timestamps on every backend (SQLite drops tzinfo on the way back)."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            raise TypeError("Refusing to store a naive datetime; use timezone-aware UTC.")
        return value.astimezone(dt.UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return None
        stamp: dt.datetime = value
        return stamp.replace(tzinfo=dt.UTC) if stamp.tzinfo is None else stamp.astimezone(dt.UTC)

    def __repr__(self) -> str:
        return "UTCDateTime()"
