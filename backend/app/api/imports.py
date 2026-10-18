"""Smart Importer: detect a statement, preview normalized transactions, then commit them."""

import hashlib
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, MarketService, get_owned_account
from app.config import get_settings
from app.enums import AccountType, ImportSource
from app.models import Account, CustomCSVMapping, ImportLog, User
from app.parsers import (
    BaseBrokerParser,
    ColumnMappingConfig,
    GenericCSVParser,
    SourceFile,
    UnsupportedFileError,
    detect_parser,
    get_parser,
)
from app.parsers.base import AccountHint, ParsedRow, ParseResult
from app.parsers.generic import TablePreview, build_table_preview
from app.parsers.presets import TABULAR_KINDS
from app.schemas.api import (
    Detection,
    ImportCommitRequest,
    ImportCommitResult,
    ImportLogOut,
    ImportPreview,
    MappingRef,
    PreviewGroup,
    PreviewSummary,
    PreviewTransaction,
    SkippedFile,
)
from app.services.ingestion import AccountNotFoundError, find_duplicates, ingest_transactions, record_failed_import

router = APIRouter(prefix="/api/import", tags=["import"])
GENERIC_KEY = "generic"
MAX_ERRORS = 200
MAX_FILES = 500


async def _read_upload(file: UploadFile) -> SourceFile:
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Files are limited to {get_settings().max_upload_mb} MB."
        )
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    return SourceFile(file.filename or "upload", content)


def _table_preview(source: SourceFile, config: ColumnMappingConfig | None = None) -> TablePreview | None:
    if source.kind not in TABULAR_KINDS:
        return None
    try:
        table = GenericCSVParser(config).table_for(source) if config else source.table
        return build_table_preview(table, config.header_row if config else None)
    except (UnsupportedFileError, ValueError):
        return None


def _same_broker(hint_broker: str, account_broker: str) -> bool:
    """'Erste Bank' matches 'Erste NetBroker', 'Interactive Brokers' matches 'Interactive Brokers LLC'."""
    first = hint_broker.split(maxsplit=1)[0].casefold() if hint_broker.split() else ""
    return bool(first) and first in account_broker.casefold()


def _suggest_account(
    session: DbSession, user: User, hint: AccountHint | None, *, one_of_many: bool = False
) -> int | None:
    """The account a statement (or one sub-account of it) most likely belongs to.

    `one_of_many`: the hint is one of several accounts in the same import, so "the only account at this broker"
    is no evidence; only an account ID or a TBSZ vintage can match.
    """
    if hint is None:
        return None
    accounts = list(session.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))))
    if hint.external_account_id:
        for account in accounts:
            if account.external_account_id and account.external_account_id == hint.external_account_id:
                return account.id
    if hint.tbsz_year is not None:
        vintage = [a for a in accounts if a.account_type is AccountType.TBSZ and a.tbsz_year == hint.tbsz_year]
        if hint.broker:
            vintage = [a for a in vintage if _same_broker(hint.broker, a.broker)]
        return vintage[0].id if len(vintage) == 1 else None
    if hint.broker and not one_of_many:
        matches = [a for a in accounts if a.broker.casefold() == hint.broker.casefold()]
        if len(matches) == 1:
            return matches[0].id
    return None


def _group_overrides(session: DbSession, user: User, raw: str | None) -> dict[str, int | None]:
    """{group key: account id, or null to leave the group out}, as chosen in the preview."""
    if not raw:
        return {}
    try:
        overrides = TypeAdapter(dict[str, int | None]).validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid group_accounts") from exc
    for account_id in overrides.values():
        if account_id is not None:
            get_owned_account(session, user, account_id)
    return overrides


def _grouped(
    session: DbSession,
    user: User,
    parsed: list[tuple[BaseBrokerParser, ParseResult]],
    overrides: dict[str, int | None],
    preview: ImportPreview,
) -> None:
    """Fill `preview` with rows grouped by target account, each checked for duplicates against its account."""
    rows: dict[str, list[ParsedRow]] = {}
    groups: dict[str, PreviewGroup] = {}
    for parser, result in parsed:
        for row in result.rows:
            key = f"{parser.key}:{row.account}" if row.account else parser.key
            if key not in groups:
                hint = result.accounts.get(row.account) if row.account else result.account_hint
                label = (hint.name or hint.external_account_id) if hint else None
                groups[key] = PreviewGroup(
                    key=key,
                    label=label or parser.label,
                    parser_key=parser.key,
                    account_hint=hint,
                    suggested_account_id=None,
                    summary=PreviewSummary(total=0, new=0, duplicates=0, errors=0),
                )
            rows.setdefault(key, []).append(row)
        preview.errors += result.errors[: MAX_ERRORS - len(preview.errors)]
        preview.warnings += result.warnings
        preview.summary.errors += len(result.errors)
    for key, group in groups.items():
        group.suggested_account_id = (
            overrides[key]
            if key in overrides
            else _suggest_account(session, user, group.account_hint, one_of_many=len(groups) > 1)
        )
        transactions = [row.transaction for row in rows[key]]
        target = group.suggested_account_id
        duplicates = find_duplicates(session, target, transactions) if target else [False] * len(transactions)
        preview.transactions += [
            PreviewTransaction(row=row.row, duplicate=duplicate, transaction=row.transaction, group=key)
            for row, duplicate in zip(rows[key], duplicates, strict=True)
        ]
        group.summary = PreviewSummary(
            total=len(transactions), new=len(transactions) - sum(duplicates), duplicates=sum(duplicates), errors=0
        )
        preview.summary.total += group.summary.total
        preview.summary.new += group.summary.new
        preview.summary.duplicates += group.summary.duplicates
    preview.groups = list(groups.values())
    preview.status = "parsed"


def _resolve_config(
    session: DbSession, user: User, mapping_id: int | None, mapping_json: str | None
) -> tuple[ColumnMappingConfig, MappingRef | None] | None:
    if mapping_json:
        try:
            return ColumnMappingConfig.model_validate_json(mapping_json), None
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid mapping: {exc.errors()}") from exc
    if mapping_id is not None:
        saved = session.get(CustomCSVMapping, mapping_id)
        if saved is None or saved.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping preset not found")
        return ColumnMappingConfig.model_validate(saved.config), MappingRef(id=saved.id, name=saved.name)
    return None


@router.post("/preview", response_model=ImportPreview)
async def preview_import(
    session: DbSession,
    user: CurrentUser,
    files: Annotated[list[UploadFile], File(description="One statement, or many (e.g. a folder of daily reports)")],
    account_id: Annotated[int | None, Form()] = None,
    parser_key: Annotated[str | None, Form()] = None,
    mapping_id: Annotated[int | None, Form()] = None,
    mapping: Annotated[str | None, Form(description="ColumnMappingConfig JSON")] = None,
    group_accounts: Annotated[str | None, Form(description="JSON {group key: account id or null}")] = None,
) -> ImportPreview:
    if not files or len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Upload between 1 and {MAX_FILES} files at once.")
    if account_id is not None:
        get_owned_account(session, user, account_id)
    overrides = _group_overrides(session, user, group_accounts)
    sources = [await _read_upload(file) for file in files]
    if len(sources) == 1:
        return _preview_file(session, user, sources[0], account_id, parser_key, mapping_id, mapping, overrides)
    return _preview_files(session, user, sources, overrides)


def _preview_files(
    session: DbSession, user: User, sources: list[SourceFile], overrides: dict[str, int | None]
) -> ImportPreview:
    """Many statements at once: each recognized by a preset, rows grouped by the account they belong to."""
    digest = hashlib.sha256("".join(sorted(s.sha256 for s in sources)).encode()).hexdigest()
    preview = ImportPreview(
        status="unsupported",
        filename=f"{len(sources)} files",
        file_sha256=digest,
        file_kind="multiple",
        file_count=len(sources),
    )
    parsed: list[tuple[BaseBrokerParser, ParseResult]] = []
    first_by_digest: dict[str, str] = {}
    for source in sources:
        if (original := first_by_digest.setdefault(source.sha256, source.filename)) != source.filename:
            preview.skipped_files.append(SkippedFile(filename=source.filename, reason=f"Same file as {original}"))
            continue
        if source.kind in ("pdf", "unknown"):
            preview.skipped_files.append(SkippedFile(filename=source.filename, reason="Not a CSV, Excel or XML file"))
            continue
        detection = detect_parser(source)
        if detection is None:
            reason = "Not a recognized statement; import it on its own to map its columns"
            preview.skipped_files.append(SkippedFile(filename=source.filename, reason=reason))
            continue
        try:
            parsed.append((detection.parser, detection.parser.run(source)))
        except (UnsupportedFileError, ValueError) as exc:
            preview.skipped_files.append(SkippedFile(filename=source.filename, reason=f"Couldn't read it: {exc}"))
    if parsed:
        preview.detection = Detection(
            parser_key=parsed[0][0].key, parser_label=parsed[0][0].label, broker=parsed[0][0].broker, confidence=1
        )
        _grouped(session, user, parsed, overrides, preview)
    if not preview.transactions:
        preview.status = "unsupported"
        preview.message = "None of these files contained transactions Jacklyn could read."
    return preview


def _preview_file(
    session: DbSession,
    user: User,
    source: SourceFile,
    account_id: int | None,
    parser_key: str | None,
    mapping_id: int | None,
    mapping: str | None,
    overrides: dict[str, int | None],
) -> ImportPreview:
    preview = ImportPreview(
        status="needs_mapping", filename=source.filename, file_sha256=source.sha256, file_kind=source.kind
    )
    if source.kind == "pdf":
        preview.status = "unsupported"
        preview.message = "PDF statements aren't supported yet. Export the statement as CSV or Excel instead."
        return preview
    if source.kind == "unknown":
        preview.status = "unsupported"
        preview.message = "This file type isn't recognized. Upload a CSV, Excel (.xlsx/.xls) or IBKR Flex XML file."
        return preview

    parser: BaseBrokerParser | None = None
    resolved = _resolve_config(session, user, mapping_id, mapping)
    if resolved is not None:
        config, preview.mapping_used = resolved
        parser = GenericCSVParser(config)
        preview.table = _table_preview(source, config)
    elif parser_key == GENERIC_KEY:
        preview.table = _table_preview(source)
    elif parser_key:
        parser = get_parser(parser_key)
        if parser is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown parser '{parser_key}'")
        preview.detection = Detection(
            parser_key=parser.key, parser_label=parser.label, broker=parser.broker, confidence=1
        )
    else:
        detection = detect_parser(source)
        if detection is not None:
            parser = detection.parser
            preview.detection = Detection(
                parser_key=parser.key,
                parser_label=parser.label,
                broker=parser.broker,
                confidence=round(detection.confidence, 2),
            )
        preview.table = _table_preview(source)
        if parser is None and preview.table is not None:
            saved = session.scalar(
                select(CustomCSVMapping)
                .where(
                    CustomCSVMapping.user_id == user.id,
                    CustomCSVMapping.header_signature == preview.table.header_signature,
                )
                .order_by(CustomCSVMapping.updated_at.desc())
            )
            if saved is not None:
                parser = GenericCSVParser(ColumnMappingConfig.model_validate(saved.config))
                preview.mapping_used = MappingRef(id=saved.id, name=saved.name)

    if parser is None:
        if preview.table is None:
            preview.status = "unsupported"
            preview.message = "Couldn't read a table from this file."
        else:
            preview.message = "Unrecognized format — map the columns once and save it as a preset."
        return preview

    try:
        result: ParseResult = parser.run(source)
    except (UnsupportedFileError, ValueError) as exc:
        preview.status = "unsupported"
        preview.message = f"Couldn't parse the file: {exc}"
        return preview

    if len(result.accounts) > 1:  # one statement covering several accounts (Erste sub-accounts, a Flex query)
        _grouped(session, user, [(parser, result)], overrides, preview)
        return preview
    preview.status = "parsed"
    preview.account_hint = result.account_hint
    preview.suggested_account_id = account_id or _suggest_account(session, user, result.account_hint)
    target = preview.suggested_account_id
    transactions = result.transactions
    duplicates = find_duplicates(session, target, transactions) if target is not None else [False] * len(transactions)
    preview.transactions = [
        PreviewTransaction(row=parsed.row, duplicate=duplicate, transaction=parsed.transaction)
        for parsed, duplicate in zip(result.rows, duplicates, strict=True)
    ]
    preview.errors = result.errors[:MAX_ERRORS]
    preview.warnings = result.warnings
    preview.summary = PreviewSummary(
        total=len(transactions),
        new=len(transactions) - sum(duplicates),
        duplicates=sum(duplicates),
        errors=len(result.errors),
    )
    if not transactions and result.errors:
        preview.message = "No transactions could be read. Check the column mapping."
    return preview


@router.post("/commit", response_model=ImportCommitResult)
def commit_import(
    payload: ImportCommitRequest, session: DbSession, user: CurrentUser, market: MarketService
) -> ImportCommitResult:
    get_owned_account(session, user, payload.account_id)
    try:
        outcome = ingest_transactions(
            session,
            user_id=user.id,
            account_id=payload.account_id,
            transactions=payload.transactions,
            source=ImportSource.FILE,
            parser_key=payload.parser_key,
            filename=payload.filename,
            file_sha256=payload.file_sha256,
        )
    except AccountNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except Exception as exc:
        record_failed_import(
            session,
            user_id=user.id,
            account_id=payload.account_id,
            source=ImportSource.FILE,
            message=str(exc),
            parser_key=payload.parser_key,
            filename=payload.filename,
            file_sha256=payload.file_sha256,
        )
        raise
    if outcome.imported:
        market.holdings_changed()
    return ImportCommitResult(
        import_log_id=outcome.import_log_id,
        received=outcome.received,
        imported=outcome.imported,
        duplicates=outcome.duplicates,
    )


@router.get("/logs", response_model=list[ImportLogOut])
def list_import_logs(session: DbSession, user: CurrentUser, limit: int = 50) -> list[ImportLogOut]:
    logs = session.scalars(
        select(ImportLog).where(ImportLog.user_id == user.id).order_by(ImportLog.id.desc()).limit(min(limit, 200))
    )
    return [ImportLogOut.model_validate(log) for log in logs]
