"""User-scoped lookups. All reads of user-owned rows go through here."""

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Account, CustomCSVMapping, ImportLog
from app.models.base import UserOwnedMixin


def owned[T: UserOwnedMixin](model: type[T], user_id: int) -> Select[T]:
    """``SELECT model WHERE user_id = :user_id`` — the base of every tenant query."""
    return select(model).where(model.user_id == user_id)


def get_owned_or_404[T: UserOwnedMixin](
    db: Session, model: type[T], user_id: int, obj_id: int
) -> T:
    obj = db.scalars(owned(model, user_id).where(model.id == obj_id)).first()  # type: ignore[attr-defined]
    if obj is None:
        # 404 rather than 403: don't reveal that another user's row exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
    return obj


def get_account(db: Session, user_id: int, account_id: int) -> Account:
    return get_owned_or_404(db, Account, user_id, account_id)


def get_mapping(db: Session, user_id: int, mapping_id: int) -> CustomCSVMapping:
    return get_owned_or_404(db, CustomCSVMapping, user_id, mapping_id)


def get_import_log(db: Session, user_id: int, log_id: int) -> ImportLog:
    return get_owned_or_404(db, ImportLog, user_id, log_id)
