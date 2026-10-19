"""Tier 3 entry point: every source (file upload, API sync, seeder, future webhooks) commits through here."""

import hashlib
import itertools
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.enums import ImportSource, ImportStatus
from app.models import Account, DeletedTransaction, ImportLog, Transaction
from app.schemas.standard import StandardTransaction
from app.services.assets import AssetResolver

_CHUNK = 500


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def content_key(transaction: StandardTransaction) -> str:
    return "|".join(
        (
            transaction.date.isoformat(),
            transaction.type.value,
            transaction.isin or "",
            transaction.symbol or "",
            _fmt(transaction.quantity),
            _fmt(transaction.unit_price),
            _fmt(transaction.amount),
            _fmt(transaction.fee),
            _fmt(transaction.tax),
            transaction.currency,
        )
    )


def dedup_hashes(transactions: Sequence[StandardTransaction]) -> list[str]:
    """Deterministic SHA-256 per row.

    Identical rows inside one batch (e.g. two equal buys on the same day) get an occurrence
    suffix, so they stay distinct while re-importing the same file still maps to the same hashes.
    """
    seen: Counter[str] = Counter()
    hashes: list[str] = []
    for transaction in transactions:
        key = content_key(transaction)
        occurrence = seen[key]
        seen[key] += 1
        hashes.append(_digest(key, occurrence))
    return hashes


def _digest(key: str, occurrence: int) -> str:
    return hashlib.sha256(f"{key}#{occurrence}".encode()).hexdigest()


def unused_hashes(session: Session, account_id: int, transactions: Sequence[StandardTransaction]) -> list[str]:
    """Like `dedup_hashes`, but each skips occurrences the account already has: for rows kept on purpose although
    an identical one is recorded (a second equal trade entered by hand)."""
    taken = set(session.scalars(select(Transaction.dedup_hash).where(Transaction.account_id == account_id)))
    hashes: list[str] = []
    for transaction in transactions:
        key = content_key(transaction)
        digest = next(d for n in itertools.count() if (d := _digest(key, n)) not in taken)
        taken.add(digest)
        hashes.append(digest)
    return hashes


def _external_key(transaction: StandardTransaction) -> tuple[str, str, str] | None:
    if not transaction.external_id:
        return None
    return transaction.external_id, transaction.type.value, transaction.currency


def _chunks[T](items: Sequence[T]) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), _CHUNK):
        yield items[start : start + _CHUNK]


def _existing(
    session: Session,
    account_id: int,
    transactions: Sequence[StandardTransaction],
    hashes: list[str],
    include_deleted: bool,
) -> tuple[set[str], set[tuple[str, str, str]]]:
    known_hashes: set[str] = set()
    known_external: set[tuple[str, str, str]] = set()
    external_keys = [key for t in transactions if (key := _external_key(t))]
    tables: list[type[Transaction] | type[DeletedTransaction]] = [Transaction]
    if include_deleted:
        tables.append(DeletedTransaction)
    for table in tables:
        for chunk in _chunks(hashes):
            known_hashes.update(
                session.scalars(
                    select(table.dedup_hash).where(table.account_id == account_id, table.dedup_hash.in_(chunk))
                )
            )
        for key_chunk in _chunks(external_keys):
            rows = session.execute(
                select(table.external_id, table.type, table.currency).where(
                    table.account_id == account_id,
                    tuple_(table.external_id, table.type, table.currency).in_(
                        [(ext, tx_type, currency) for ext, tx_type, currency in key_chunk]
                    ),
                )
            )
            known_external.update((ext or "", str(tx_type), currency) for ext, tx_type, currency in rows)
    return known_hashes, known_external


def find_duplicates(
    session: Session, account_id: int, transactions: Sequence[StandardTransaction], *, include_deleted: bool = True
) -> list[bool]:
    """Per transaction: is it already recorded on this account (or repeated earlier in the batch)?

    Rows the user deleted count as recorded too, so a re-import doesn't bring them back.
    """
    hashes = dedup_hashes(transactions)
    known_hashes, known_external = _existing(session, account_id, transactions, hashes, include_deleted)
    flags: list[bool] = []
    batch_external: set[tuple[str, str, str]] = set()
    for transaction, digest in zip(transactions, hashes, strict=True):
        external = _external_key(transaction)
        duplicate = digest in known_hashes or (
            external is not None and (external in known_external or external in batch_external)
        )
        if external is not None:
            batch_external.add(external)
        flags.append(duplicate)
    return flags


@dataclass
class IngestOutcome:
    import_log_id: int
    received: int
    imported: int
    duplicates: int
    transaction_ids: list[int] = field(default_factory=list)


class AccountNotFoundError(LookupError):
    pass


def ingest_transactions(
    session: Session,
    *,
    user_id: int,
    account_id: int,
    transactions: Sequence[StandardTransaction],
    source: ImportSource,
    parser_key: str | None = None,
    filename: str | None = None,
    file_sha256: str | None = None,
    message: str | None = None,
    keep_duplicates: bool = False,
) -> IngestOutcome:
    """Idempotently persist normalized transactions for one account and record an ImportLog.

    `keep_duplicates` stores every row, even one identical to a recorded row (manual entry, after the user
    confirmed it): each gets a fingerprint the account doesn't have yet.
    """
    account = session.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise AccountNotFoundError(f"Account {account_id} not found")

    if keep_duplicates:
        duplicates = [False] * len(transactions)
        hashes = unused_hashes(session, account_id, transactions)
    else:
        duplicates = find_duplicates(session, account_id, transactions)
        hashes = dedup_hashes(transactions)
    log = ImportLog(
        user_id=user_id,
        account_id=account_id,
        source=source,
        status=ImportStatus.COMMITTED,
        parser_key=parser_key,
        filename=filename,
        file_sha256=file_sha256,
        rows_received=len(transactions),
        message=message,
    )
    session.add(log)
    session.flush()

    resolver = AssetResolver(session)
    new_rows: list[Transaction] = []
    # Insert in date order so assets are created by their first trade, not a later dividend.
    order = sorted(range(len(transactions)), key=lambda index: (transactions[index].date, index))
    for index in order:
        if duplicates[index]:
            continue
        transaction = transactions[index]
        asset = resolver.resolve(transaction)
        row = Transaction(
            user_id=user_id,
            account_id=account_id,
            asset_id=asset.id if asset else None,
            import_log_id=log.id,
            trade_date=transaction.date,
            type=transaction.type,
            quantity=transaction.quantity,
            unit_price=transaction.unit_price,
            amount=transaction.amount,
            fee=transaction.fee,
            tax=transaction.tax,
            currency=transaction.currency,
            description=transaction.description or transaction.name,
            external_id=transaction.external_id,
            dedup_hash=hashes[index],
        )
        session.add(row)
        new_rows.append(row)

    session.flush()
    log.rows_imported = len(new_rows)
    log.rows_duplicate = sum(duplicates)
    session.commit()
    return IngestOutcome(
        import_log_id=log.id,
        received=len(transactions),
        imported=len(new_rows),
        duplicates=sum(duplicates),
        transaction_ids=[row.id for row in new_rows],
    )


def record_failed_import(
    session: Session,
    *,
    user_id: int,
    account_id: int | None,
    source: ImportSource,
    message: str,
    parser_key: str | None = None,
    filename: str | None = None,
    file_sha256: str | None = None,
) -> None:
    session.rollback()
    session.add(
        ImportLog(
            user_id=user_id,
            account_id=account_id,
            source=source,
            status=ImportStatus.FAILED,
            parser_key=parser_key,
            filename=filename,
            file_sha256=file_sha256,
            message=message[:2000],
        )
    )
    session.commit()
