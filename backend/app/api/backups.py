"""Admin-only database backups: the file holds every user's data, so only admins can download or restore it."""

import datetime as dt
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import AdminUser, Backups, MarketService
from app.config import get_settings
from app.services.backups import BackupError, BackupFile

router = APIRouter(prefix="/api/admin/backups", tags=["admin"])
RESTORE_CONFIRMATION = "RESTORE"
_CHUNK = 1024 * 1024


class BackupOut(BaseModel):
    name: str
    kind: str
    size: int
    created_at: dt.datetime


class BackupsOut(BaseModel):
    supported: bool  # SQLite; PostgreSQL deployments use pg_dump
    automatic: bool  # a daily snapshot is kept
    folder: str
    backups: list[BackupOut]


class RestoreOut(BaseModel):
    safety_backup: BackupOut  # the data as it was just before, in case the restore was a mistake


def _out(backup: BackupFile) -> BackupOut:
    return BackupOut(name=backup.name, kind=backup.kind, size=backup.size, created_at=backup.created_at)


def _bad(exc: BackupError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("", response_model=BackupsOut)
def list_backups(_admin: AdminUser, backups: Backups) -> BackupsOut:
    return BackupsOut(
        supported=backups.supported,
        automatic=backups.supported and get_settings().auto_backups,
        folder=str(backups.folder),
        backups=[_out(backup) for backup in backups.list()],
    )


@router.post("", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def create_backup(_admin: AdminUser, backups: Backups) -> BackupOut:
    try:
        return _out(backups.create("manual"))
    except BackupError as exc:
        raise _bad(exc) from exc


@router.get("/{name}", response_class=FileResponse)
def download_backup(name: str, _admin: AdminUser, backups: Backups) -> FileResponse:
    try:
        path = backups.path(name)
    except BackupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=name)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(name: str, _admin: AdminUser, backups: Backups) -> None:
    try:
        backups.delete(name)
    except BackupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/restore", response_model=RestoreOut)
async def restore_backup(
    _admin: AdminUser,
    backups: Backups,
    market: MarketService,
    file: Annotated[UploadFile, File()],
    confirm: Annotated[str, Form()],
) -> RestoreOut:
    """Replace the whole database with an uploaded backup. Everyone is signed out unless the backup knows them."""
    if confirm != RESTORE_CONFIRMATION:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Type {RESTORE_CONFIRMATION} to confirm.")
    limit = get_settings().max_restore_mb * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="jacklyn-restore-") as folder:
        upload = Path(folder) / "upload.db"
        written = 0
        with upload.open("wb") as handle:
            while chunk := await file.read(_CHUNK):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "That backup is larger than allowed.")
                handle.write(chunk)
        try:
            safety = backups.restore(upload)
        except BackupError as exc:
            raise _bad(exc) from exc
    market.holdings_changed()
    return RestoreOut(safety_backup=_out(safety))
