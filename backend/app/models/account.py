from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UserOwnedMixin, str_enum
from app.models.enums import AccountType, Institution

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.user import User


class Account(UserOwnedMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # Target for composite FKs so child rows can't point at another user's account.
        UniqueConstraint("id", "user_id"),
        UniqueConstraint("user_id", "name"),
        CheckConstraint(
            "(account_type = 'tbsz' AND tbsz_year IS NOT NULL)"
            " OR (account_type <> 'tbsz' AND tbsz_year IS NULL)",
            name="tbsz_year_matches_type",
        ),
        CheckConstraint(
            "tbsz_year IS NULL OR (tbsz_year >= 1995 AND tbsz_year <= 2100)",
            name="tbsz_year_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[Institution] = mapped_column(str_enum(Institution))
    account_type: Mapped[AccountType] = mapped_column(
        str_enum(AccountType), default=AccountType.STANDARD
    )
    tbsz_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Transaction.account_id",
        overlaps="transactions",
    )
