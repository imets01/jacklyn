"""Smart Importer: detect a statement, preview normalized transactions, then commit them."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, get_owned_account
from app.config import get_settings
from app.enums import ImportSource
from app.models import Account, CustomCSVMapping, ImportLog, User
from app.parsers import (
    PRESET_PARSERS,
    BaseBrokerParser,
    ColumnMappingConfig,
    GenericCSVParser,
    SourceFile,
    UnsupportedFileError,
    detect_parser,
    get_parser,
)
from app.parsers.base import AccountHint, ParseResult
from app.parsers.generic import TablePreview, build_table_preview
from app.parsers.presets import TABULAR_KINDS
from app.schemas.api import (
    Detection,
    ImportCommitRequest,
    ImportCommitResult,
    ImportLogOut,
    ImportPreview,
    MappingRef,
    ParserInfo,
    PreviewSummary,
    PreviewTransaction,
)
from app.services.ingestion import AccountNotFoundError, find_duplicates, ingest_transactions, record_failed_import

router = APIRouter(prefix="/api/import", tags=["import"])
GENERIC_KEY = "generic"
MAX_ERRORS = 200


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


def _suggest_account(session: DbSession, user: User, hint: AccountHint | None) -> int | None:
    if hint is None:
        return None
    accounts = list(session.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))))
    if hint.external_account_id:
        for account in accounts:
            if account.external_account_id and account.external_account_id == hint.external_account_id:
                return account.id
    if hint.broker:
        matches = [a for a in accounts if a.broker.casefold() == hint.broker.casefold()]
        if len(matches) == 1:
            return matches[0].id
    return None


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


@router.get("/parsers", response_model=list[ParserInfo])
def list_parsers() -> list[ParserInfo]:
    return [ParserInfo(key=p.key, label=p.label, broker=p.broker) for p in PRESET_PARSERS]


@router.post("/preview", response_model=ImportPreview)
async def preview_import(
    session: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    account_id: Annotated[int | None, Form()] = None,
    parser_key: Annotated[str | None, Form()] = None,
    mapping_id: Annotated[int | None, Form()] = None,
    mapping: Annotated[str | None, Form(description="ColumnMappingConfig JSON")] = None,
) -> ImportPreview:
    source = await _read_upload(file)
    if account_id is not None:
        get_owned_account(session, user, account_id)
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
def commit_import(payload: ImportCommitRequest, session: DbSession, user: CurrentUser) -> ImportCommitResult:
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
