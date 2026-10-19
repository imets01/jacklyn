"""The ledger: queries shared by the per-account list and the transactions page, and edits made by hand."""

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.enums import ImportSource, TransactionType
from app.models import Account, Asset, DeletedTransaction, ImportLog, Transaction
from app.schemas.api import AssetOption, TransactionOut, TransactionPage
from app.schemas.standard import StandardTransaction
from app.services.assets import AssetResolver
from app.services.ingestion import unused_hashes


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
        select(Transaction, Asset, Account.name, ImportLog.source)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Asset, Asset.id == Transaction.asset_id)
        .outerjoin(ImportLog, ImportLog.id == Transaction.import_log_id)
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
                manual=source is ImportSource.MANUAL,
            )
            for tx, asset, account_name, source in rows
        ],
    )


class TransactionNotFoundError(LookupError):
    pass


def _owned(session: Session, user_id: int, transaction_id: int) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user_id:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found")
    return transaction


def _is_manual(session: Session, transaction: Transaction) -> bool:
    log = session.get(ImportLog, transaction.import_log_id) if transaction.import_log_id else None
    return log is not None and log.source is ImportSource.MANUAL


def _remember_deleted(session: Session, transaction: Transaction) -> None:
    """Keep a broker row's fingerprint, so the next import or sync of the same statement skips it.

    Rows entered by hand need none: no statement will bring them back.
    """
    if _is_manual(session, transaction):
        return
    known = session.scalar(
        select(DeletedTransaction.id).where(
            DeletedTransaction.account_id == transaction.account_id,
            DeletedTransaction.dedup_hash == transaction.dedup_hash,
        )
    )
    if known is None:
        session.add(
            DeletedTransaction(
                user_id=transaction.user_id,
                account_id=transaction.account_id,
                type=transaction.type,
                currency=transaction.currency,
                external_id=transaction.external_id,
                dedup_hash=transaction.dedup_hash,
            )
        )


def edit_transaction(
    session: Session, user_id: int, transaction_id: int, account_id: int, values: StandardTransaction
) -> Transaction:
    """Overwrite a transaction with corrected values.

    It keeps its fingerprint and broker ID, so re-importing the original statement still recognizes it and the
    correction stands. Moved to another account, it counts as deleted from the first one.
    """
    transaction = _owned(session, user_id, transaction_id)
    if account_id != transaction.account_id:
        _remember_deleted(session, transaction)
        if session.scalar(
            select(Transaction.id).where(
                Transaction.account_id == account_id, Transaction.dedup_hash == transaction.dedup_hash
            )
        ):
            transaction.dedup_hash = unused_hashes(session, account_id, [values])[0]
        transaction.account_id = account_id
    asset = AssetResolver(session).resolve(values)
    transaction.asset_id = asset.id if asset else None
    transaction.trade_date = values.date
    transaction.type = values.type
    transaction.quantity = values.quantity
    transaction.unit_price = values.unit_price
    transaction.amount = values.amount
    transaction.fee = values.fee
    transaction.tax = values.tax
    transaction.currency = values.currency
    transaction.description = values.description or values.name
    session.commit()
    return transaction


def delete_transaction(session: Session, user_id: int, transaction_id: int) -> None:
    transaction = _owned(session, user_id, transaction_id)
    _remember_deleted(session, transaction)
    session.delete(transaction)
    session.commit()


def asset_options(session: Session, user_id: int, search: str | None, limit: int = 20) -> list[AssetOption]:
    """Assets the user already has transactions in, for the manual entry form.

    Only their own: assets are shared reference data, and suggesting others' would tell what other people hold.
    """
    query = (
        select(Asset)
        .where(Asset.id.in_(select(Transaction.asset_id).where(Transaction.user_id == user_id)))
        .order_by(Asset.symbol)
        .limit(limit)
    )
    if search and (term := search.strip()):
        pattern = _like(term)
        query = query.where(
            or_(*(column.ilike(pattern, escape="\\") for column in (Asset.symbol, Asset.name, Asset.isin)))
        )
    return [
        AssetOption(
            id=asset.id,
            symbol=asset.symbol,
            name=asset.name,
            isin=asset.isin,
            currency=asset.currency,
            asset_class=asset.asset_class,
        )
        for asset in session.scalars(query)
    ]
