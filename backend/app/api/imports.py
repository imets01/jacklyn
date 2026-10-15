from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models import CustomCSVMapping, ImportLog, TransactionType
from app.parsers import ALL_PARSERS, ColumnMapping
from app.parsers.generic_csv import CANONICAL_FIELDS
from app.schemas import (
    ImportCommitOut,
    ImportLogOut,
    ImportOptionsOut,
    ImportPreviewOut,
    MappingOut,
    ParserInfo,
    PreviewCounts,
    PreviewRowOut,
)
from app.services import importer
from app.services.tenancy import get_account, get_mapping, owned

router = APIRouter(prefix="/import", tags=["import"])

FileField = Annotated[UploadFile, File(description="Broker export (CSV)")]
AccountField = Annotated[int, Form()]
ParserField = Annotated[str, Form(description="'auto', 'generic' or a parser key")]
MappingField = Annotated[
    str | None, Form(description="ColumnMapping JSON; implies the generic parser")
]
MappingIdField = Annotated[int | None, Form()]


async def _read_upload(upload: UploadFile) -> bytes:
    limit = get_settings().max_upload_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {limit // (1024 * 1024)} MB"
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")
    return data


def _parse_mapping(raw: str | None) -> ColumnMapping | None:
    if not raw:
        return None
    try:
        return ColumnMapping.model_validate_json(raw)
    except ValidationError as exc:
        messages = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid mapping: {messages}"
        ) from exc


async def _request(
    db: DbSession,
    user: CurrentUser,
    file: UploadFile,
    account_id: int,
    parser: str,
    mapping: str | None,
    mapping_id: int | None,
) -> importer.ImportRequest:
    return importer.ImportRequest(
        filename=file.filename or "upload.csv",
        data=await _read_upload(file),
        account=get_account(db, user.id, account_id),
        parser_key=parser,
        mapping=_parse_mapping(mapping),
        mapping_id=mapping_id,
    )


@router.get("/options", response_model=ImportOptionsOut)
def import_options() -> ImportOptionsOut:
    return ImportOptionsOut(
        parsers=[
            ParserInfo(key=p.key, label=p.label, institution=p.institution, is_stub=p.is_stub)
            for p in ALL_PARSERS
        ],
        fields=CANONICAL_FIELDS,
        transaction_types=list(TransactionType),
        max_upload_bytes=get_settings().max_upload_bytes,
    )


@router.post("/preview", response_model=ImportPreviewOut)
async def import_preview(
    db: DbSession,
    user: CurrentUser,
    file: FileField,
    account_id: AccountField,
    parser: ParserField = "auto",
    mapping: MappingField = None,
    mapping_id: MappingIdField = None,
) -> ImportPreviewOut:
    req = await _request(db, user, file, account_id, parser, mapping, mapping_id)
    try:
        analysis = importer.analyse(db, user, req)
    except importer.ImportFailed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    prep, result = analysis.prepared, analysis.result
    rows: list[PreviewRowOut] = []
    counts = {"new": 0, "duplicate": 0, "error": 0}
    for row in importer.preview_rows(analysis):
        counts[row.status] += 1
        if len(rows) >= importer.PREVIEW_ROW_LIMIT:
            continue
        tx = row.tx
        rows.append(
            PreviewRowOut(row_number=row.row_number, status=row.status, message=row.message)
            if tx is None
            else PreviewRowOut(
                row_number=row.row_number,
                status=row.status,
                type=tx.type,
                trade_date=tx.trade_date,
                symbol=tx.symbol,
                isin=tx.isin,
                name=tx.asset_name,
                quantity=tx.quantity,
                price=tx.price,
                amount=tx.amount,
                fee=tx.fee,
                currency=tx.currency,
                description=tx.description,
            )
        )
    total = sum(counts.values())
    return ImportPreviewOut(
        filename=req.filename,
        file_sha256=prep.sha256,
        account_id=req.account.id,
        parser_key=prep.parser.key if prep.parser else None,
        parser_label=prep.parser.label if prep.parser else None,
        confidence=prep.confidence,
        is_stub=prep.parser.is_stub if prep.parser else False,
        mapping_id=prep.mapping_id,
        needs_mapping=prep.parser is None,
        headers=prep.sample.headers,
        sample_rows=prep.sample.rows[:10],
        suggestion=prep.suggestion,
        counts=PreviewCounts(total=total, **counts),
        rows=rows,
        rows_truncated=total > len(rows),
        warnings=result.warnings if result else [],
    )


@router.post("/commit", response_model=ImportCommitOut, status_code=status.HTTP_201_CREATED)
async def import_commit(
    db: DbSession,
    user: CurrentUser,
    file: FileField,
    account_id: AccountField,
    parser: ParserField = "auto",
    mapping: MappingField = None,
    mapping_id: MappingIdField = None,
    expected_sha256: Annotated[str | None, Form()] = None,
    save_mapping_as: Annotated[str | None, Form(max_length=120)] = None,
) -> ImportCommitOut:
    req = await _request(db, user, file, account_id, parser, mapping, mapping_id)
    try:
        outcome = importer.commit(db, user, req, expected_sha256, save_mapping_as)
    except importer.ImportFailed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    log = outcome.log
    return ImportCommitOut(
        import_id=log.id,
        status=log.status,
        rows_total=log.rows_total,
        rows_imported=log.rows_imported,
        rows_duplicate=log.rows_duplicate,
        rows_failed=log.rows_failed,
        mapping_id=outcome.mapping_id,
        assets_created=outcome.assets_created,
    )


@router.get("/logs", response_model=list[ImportLogOut])
def import_logs(db: DbSession, user: CurrentUser, limit: int = 20) -> list[ImportLog]:
    query = owned(ImportLog, user.id).order_by(ImportLog.id.desc()).limit(min(limit, 100))
    return list(db.scalars(query))


@router.get("/mappings", response_model=list[MappingOut])
def list_mappings(db: DbSession, user: CurrentUser) -> list[CustomCSVMapping]:
    return list(db.scalars(owned(CustomCSVMapping, user.id).order_by(CustomCSVMapping.name)))


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(mapping_id: int, db: DbSession, user: CurrentUser) -> None:
    db.delete(get_mapping(db, user.id, mapping_id))
    db.commit()
