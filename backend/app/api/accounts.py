from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.models import Account, AccountType, Transaction
from app.schemas import AccountCreate, AccountOut, AccountUpdate, TbszOut
from app.services.tbsz import tbsz_status
from app.services.tenancy import get_account, owned

router = APIRouter(prefix="/accounts", tags=["accounts"])


def account_out(account: Account, transaction_count: int = 0) -> AccountOut:
    out = AccountOut.model_validate(account)
    out.transaction_count = transaction_count
    if account.account_type is AccountType.TBSZ and account.tbsz_year is not None:
        out.tbsz = TbszOut.model_validate(tbsz_status(account.tbsz_year))
    return out


@router.get("", response_model=list[AccountOut])
def list_accounts(db: DbSession, user: CurrentUser) -> list[AccountOut]:
    rows = db.execute(
        select(Transaction.account_id, func.count())
        .where(Transaction.user_id == user.id)
        .group_by(Transaction.account_id)
    )
    counts = {account_id: count for account_id, count in rows}
    accounts = db.scalars(owned(Account, user.id).order_by(Account.id))
    return [account_out(a, counts.get(a.id, 0)) for a in accounts]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: DbSession, user: CurrentUser) -> AccountOut:
    account = Account(user_id=user.id, **payload.model_dump())
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"An account named {payload.name!r} already exists"
        ) from exc
    return account_out(account)


@router.get("/{account_id}", response_model=AccountOut)
def read_account(account_id: int, db: DbSession, user: CurrentUser) -> AccountOut:
    account = get_account(db, user.id, account_id)
    count = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == user.id, Transaction.account_id == account.id)
    )
    return account_out(account, count or 0)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int, payload: AccountUpdate, db: DbSession, user: CurrentUser
) -> AccountOut:
    account = get_account(db, user.id, account_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Account name already in use") from exc
    return account_out(account)
