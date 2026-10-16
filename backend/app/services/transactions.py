"""Ledger queries shared by the per-account list and the filterable transactions page."""

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.enums import TransactionType
from app.models import Account, Asset, Transaction
from app.schemas.api import TransactionOut, TransactionPage


@dataclass
class TransactionFilter:
    account_ids: list[int] | None = None
    types: list[TransactionType] | None = None
    asset_id: int | None = None
    search: str | None = None  # symbol, name, ISIN or description
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    extra: list[ColumnElement[bool]] = field(default_factory=list)


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def _conditions(user_id: int, flt: TransactionFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Transaction.user_id == user_id, *flt.extra]
    if flt.account_ids:
        conditions.append(Transaction.account_id.in_(flt.account_ids))
    if flt.types:
        conditions.append(Transaction.type.in_(flt.types))
    if flt.asset_id is not None:
        conditions.append(Transaction.asset_id == flt.asset_id)
    if flt.date_from:
        conditions.append(Transaction.trade_date >= flt.date_from)
    if flt.date_to:
        conditions.append(Transaction.trade_date <= flt.date_to)
    if flt.search and (term := flt.search.strip()):
        pattern = _like(term)
        conditions.append(
            or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (Asset.symbol, Asset.name, Asset.isin, Transaction.description)
                )
            )
        )
    return conditions


def transaction_page(
    session: Session, user_id: int, flt: TransactionFilter, limit: int, offset: int
) -> TransactionPage:
    """Newest first. Every condition is scoped to the user, so foreign account ids simply match nothing."""
    conditions = _conditions(user_id, flt)
    base = (
        select(Transaction, Asset, Account.name)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Asset, Asset.id == Transaction.asset_id)
        .where(*conditions)
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.order_by(Transaction.trade_date.desc(), Transaction.id.desc()).limit(limit).offset(offset)
    ).all()
    return TransactionPage(
        total=total,
        items=[
            TransactionOut(
                id=tx.id,
                account_id=tx.account_id,
                account_name=account_name,
                date=tx.trade_date,
                type=tx.type,
                symbol=asset.symbol if asset else None,
                name=asset.name if asset else None,
                isin=asset.isin if asset else None,
                quantity=tx.quantity,
                unit_price=tx.unit_price,
                amount=tx.amount,
                fee=tx.fee,
                tax=tx.tax,
                currency=tx.currency,
                description=tx.description,
                external_id=tx.external_id,
                import_log_id=tx.import_log_id,
            )
            for tx, asset, account_name in rows
        ],
    )
