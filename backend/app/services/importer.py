"""Import orchestration: upload -> detect -> parse -> dedupe -> (preview | commit).

Preview is stateless: nothing is written. Commit re-parses the same file with
the same options inside one DB transaction and records an :class:`ImportLog`.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Asset,
    AssetClass,
    CustomCSVMapping,
    ImportLog,
    ImportStatus,
    Institution,
    Transaction,
    User,
)
from app.parsers import (
    BaseBrokerParser,
    ColumnMapping,
    FileSample,
    GenericCSVParser,
    ParsedTransaction,
    ParseResult,
    detect_parser,
    instantiate,
    suggest_mapping,
)
from app.parsers.csv_utils import build_sample, decode_bytes, header_signature
from app.parsers.generic_csv import MappingSuggestion
from app.services.fingerprint import fingerprints
from app.services.tenancy import get_mapping, owned

PREVIEW_ROW_LIMIT = 1000
_IN_CHUNK = 500


class ImportFailed(ValueError):
    """User-facing import problem (bad file, bad mapping...)."""


@dataclass(slots=True)
class ImportRequest:
    filename: str
    data: bytes
    account: Account
    parser_key: str = "auto"
    mapping: ColumnMapping | None = None
    mapping_id: int | None = None


@dataclass(slots=True)
class Prepared:
    sample: FileSample
    text: str
    sha256: str
    parser: BaseBrokerParser | None
    confidence: float
    mapping_id: int | None
    suggestion: MappingSuggestion
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Analysis:
    prepared: Prepared
    result: ParseResult | None
    fingerprints: list[str]
    duplicates: set[str]


def _prepare(db: Session, user: User, req: ImportRequest) -> Prepared:
    try:
        text = decode_bytes(req.data)
    except ValueError as exc:
        raise ImportFailed(str(exc)) from exc
    sample = build_sample(req.filename, text)
    if not sample.headers:
        raise ImportFailed("The file is empty")
    sha = hashlib.sha256(req.data).hexdigest()

    def prepared(
        parser: BaseBrokerParser | None, confidence: float = 1.0, mapping_id: int | None = None
    ) -> Prepared:
        return Prepared(
            sample=sample,
            text=text,
            sha256=sha,
            parser=parser,
            confidence=confidence,
            mapping_id=mapping_id,
            # Always offered so the column mapper can be opened pre-filled.
            suggestion=suggest_mapping(sample),
        )

    if req.mapping is not None:
        return prepared(GenericCSVParser(req.mapping))
    if req.mapping_id is not None:
        saved = get_mapping(db, user.id, req.mapping_id)
        return prepared(_mapping_parser(saved), mapping_id=saved.id)
    if req.parser_key == GenericCSVParser.key:
        return prepared(None, 0.0)
    if req.parser_key != "auto":
        try:
            return prepared(instantiate(req.parser_key))
        except KeyError as exc:
            raise ImportFailed(f"Unknown parser {req.parser_key!r}") from exc

    # Auto: the user's own saved layouts win over built-in detectors.
    signature = header_signature(sample.headers)
    matched = db.scalars(
        owned(CustomCSVMapping, user.id).where(CustomCSVMapping.header_signature == signature)
    ).first()
    if matched is not None:
        return prepared(_mapping_parser(matched), mapping_id=matched.id)

    detection = detect_parser(sample)
    if detection is None:
        return prepared(None, 0.0)
    return prepared(detection.parser(), detection.confidence)


def _mapping_parser(saved: CustomCSVMapping) -> GenericCSVParser:
    try:
        return GenericCSVParser(ColumnMapping.model_validate(saved.config))
    except ValueError as exc:
        raise ImportFailed(f"Saved mapping {saved.name!r} is invalid: {exc}") from exc


def _existing_fingerprints(db: Session, account: Account, fps: Sequence[str]) -> set[str]:
    found: set[str] = set()
    unique = list(dict.fromkeys(fps))
    for i in range(0, len(unique), _IN_CHUNK):
        chunk = unique[i : i + _IN_CHUNK]
        found.update(
            db.scalars(
                select(Transaction.fingerprint).where(
                    Transaction.user_id == account.user_id,
                    Transaction.account_id == account.id,
                    Transaction.fingerprint.in_(chunk),
                )
            )
        )
    return found


def analyse(db: Session, user: User, req: ImportRequest) -> Analysis:
    prep = _prepare(db, user, req)
    if prep.parser is None:
        return Analysis(prep, None, [], set())

    result = prep.parser.parse(prep.text)
    institution = prep.parser.institution
    if institution is not Institution.OTHER and institution is not req.account.institution:
        prep.warnings.append(
            f"This looks like a {institution.value.upper()} file but the selected account "
            f"is {req.account.institution.value.upper()}."
        )
    if prep.parser.is_stub:
        prep.warnings.append(
            f"The {prep.parser.label} parser is in beta; double-check the preview."
        )
    result.warnings.extend(prep.warnings)
    fps = fingerprints(result.transactions)
    return Analysis(prep, result, fps, _existing_fingerprints(db, req.account, fps))


# ---------------------------------------------------------------------- commit


@dataclass(slots=True)
class CommitOutcome:
    log: ImportLog
    assets_created: int
    mapping_id: int | None


class _AssetResolver:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id
        self.cache: dict[tuple[str, str], Asset] = {}
        self.created = 0

    def resolve(self, tx: ParsedTransaction) -> Asset | None:
        if not tx.has_asset:
            return None
        symbol = tx.symbol or tx.isin or ""
        key = (symbol, tx.currency)
        if key in self.cache:
            return self.cache[key]

        q = owned(Asset, self.user_id).where(Asset.currency == tx.currency)
        asset = self.db.scalars(q.where(Asset.symbol == symbol)).first()
        if asset is None and tx.isin:
            asset = self.db.scalars(q.where(Asset.isin == tx.isin)).first()
        if asset is None:
            asset = Asset(
                user_id=self.user_id,
                symbol=symbol,
                name=tx.asset_name or symbol,
                isin=tx.isin,
                asset_class=tx.asset_class or AssetClass.EQUITY,
                currency=tx.currency,
            )
            self.db.add(asset)
            self.db.flush()
            self.created += 1
        else:
            if tx.isin and not asset.isin:
                asset.isin = tx.isin
            if tx.asset_name and asset.name == asset.symbol:
                asset.name = tx.asset_name
        self.cache[key] = asset
        return asset


def _save_mapping(
    db: Session,
    user: User,
    name: str,
    mapping: ColumnMapping,
    headers: list[str],
    institution: Institution,
) -> CustomCSVMapping:
    existing = db.scalars(
        owned(CustomCSVMapping, user.id).where(CustomCSVMapping.name == name)
    ).first()
    config = mapping.model_dump(mode="json")
    signature = header_signature(headers)
    if existing is not None:
        existing.config = config
        existing.header_signature = signature
        existing.institution = institution
        return existing
    saved = CustomCSVMapping(
        user_id=user.id,
        name=name,
        institution=institution,
        header_signature=signature,
        config=config,
    )
    db.add(saved)
    db.flush()
    return saved


def persist_transactions(
    db: Session,
    user_id: int,
    account: Account,
    transactions: Sequence[ParsedTransaction],
    fps: Sequence[str],
    skip: set[str] | None = None,
    import_log_id: int | None = None,
) -> tuple[int, int, int]:
    """Insert parsed transactions (linking/creating assets). Returns (imported, skipped, assets)."""
    assets = _AssetResolver(db, user_id)
    skip = skip or set()
    imported = skipped = 0
    for tx, fp in zip(transactions, fps, strict=True):
        if fp in skip:
            skipped += 1
            continue
        asset = assets.resolve(tx)
        db.add(
            Transaction(
                user_id=user_id,
                account_id=account.id,
                asset_id=asset.id if asset else None,
                import_log_id=import_log_id,
                type=tx.type,
                trade_date=tx.trade_date,
                settle_date=tx.settle_date,
                quantity=tx.quantity,
                price=tx.price,
                amount=tx.amount,
                fee=tx.fee,
                currency=tx.currency,
                description=tx.description,
                external_id=tx.external_id,
                fingerprint=fp,
            )
        )
        imported += 1
    return imported, skipped, assets.created


def commit(
    db: Session,
    user: User,
    req: ImportRequest,
    expected_sha256: str | None = None,
    save_mapping_as: str | None = None,
) -> CommitOutcome:
    analysis = analyse(db, user, req)
    prep, result = analysis.prepared, analysis.result
    if expected_sha256 and expected_sha256 != prep.sha256:
        raise ImportFailed("The file changed since it was previewed; preview it again")
    if result is None or prep.parser is None:
        raise ImportFailed("No parser for this file; provide a column mapping")

    mapping_id = prep.mapping_id
    if save_mapping_as and isinstance(prep.parser, GenericCSVParser):
        mapping_id = _save_mapping(
            db,
            user,
            save_mapping_as.strip(),
            prep.parser.mapping,
            prep.sample.headers,
            req.account.institution,
        ).id

    log = ImportLog(
        user_id=user.id,
        account_id=req.account.id,
        mapping_id=mapping_id,
        filename=req.filename[:255],
        file_sha256=prep.sha256,
        parser_key=prep.parser.key,
        status=ImportStatus.COMMITTED,
        rows_total=result.rows_total,
        errors=[{"row": e.row_number, "message": e.message} for e in result.errors[:200]],
    )
    db.add(log)
    db.flush()

    imported, duplicate, assets_created = persist_transactions(
        db,
        user.id,
        req.account,
        result.transactions,
        analysis.fingerprints,
        skip=analysis.duplicates,
        import_log_id=log.id,
    )
    log.rows_imported = imported
    log.rows_duplicate = duplicate
    log.rows_failed = len(result.errors)
    log.committed_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ImportFailed("Import conflicted with existing data; preview again") from exc
    return CommitOutcome(log=log, assets_created=assets_created, mapping_id=mapping_id)


@dataclass(frozen=True, slots=True)
class PreviewRow:
    row_number: int
    status: Literal["new", "duplicate", "error"]
    tx: ParsedTransaction | None = None
    message: str | None = None


def preview_rows(analysis: Analysis) -> list[PreviewRow]:
    """Parsed rows and errors merged back into file order."""
    result = analysis.result
    if result is None:
        return []
    rows = [
        PreviewRow(tx.row_number, "duplicate" if fp in analysis.duplicates else "new", tx)
        for tx, fp in zip(result.transactions, analysis.fingerprints, strict=True)
    ]
    rows += [PreviewRow(e.row_number, "error", message=e.message) for e in result.errors]
    return sorted(rows, key=lambda r: r.row_number)
