"""Custom column types."""

from decimal import Decimal
from typing import Any

from sqlalchemy import Dialect, Numeric, String
from sqlalchemy.types import TypeDecorator, TypeEngine

from app.core.money import to_decimal


class SafeDecimal(TypeDecorator[Decimal]):
    """Exact decimal storage on every backend.

    PostgreSQL gets a real ``NUMERIC(28, 10)``. SQLite has no decimal type
    (``NUMERIC`` there is a float in disguise), so values are stored as their
    canonical string instead. Floats are rejected on the way in.

    Aggregations are done in Python with :class:`Decimal`, never in SQL, so the
    string storage on SQLite never leaks into arithmetic.
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
        decimal_value = to_decimal(value)
        if dialect.name == "sqlite":
            return format(decimal_value, "f")
        return decimal_value

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
