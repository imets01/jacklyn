import datetime as dt
from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def enum_column[E: StrEnum](enum_cls: type[E]) -> SAEnum:
    """Store a StrEnum by value as a portable VARCHAR (no native DB enum types to migrate)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
