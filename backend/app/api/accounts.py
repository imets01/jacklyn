from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.api.deps import BaseCurrency, CurrentUser, DbSession, get_owned_account
from app.enums import AccountType
from app.models import Account, BrokerCredential, ImportLog, Transaction
from app.schemas.api import AccountCreate, AccountUpdate
from app.schemas.portfolio import AccountSummary
from app.services.portfolio import PortfolioEngine

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _summaries(
    session: DbSession, user_id: int, base: str, account_ids: list[int] | None = None, include_archived: bool = False
) -> list[AccountSummary]:
    engine = PortfolioEngine(
        session, user_id=user_id, base_currency=base, account_ids=account_ids, include_archived=include_archived
    )
    return engine.summary().accounts


@router.get("", response_model=list[AccountSummary])
def list_accounts(
    session: DbSession, user: CurrentUser, base: BaseCurrency, include_archived: bool = False
) -> list[AccountSummary]:
    return _summaries(session, user.id, base, include_archived=include_archived)


@router.post("", response_model=AccountSummary, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, session: DbSession, user: CurrentUser, base: BaseCurrency) -> AccountSummary:
    account = Account(user_id=user.id, **payload.model_dump())
    session.add(account)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"An account named '{payload.name}' already exists.") from exc
    return _summaries(session, user.id, base, [account.id])[0]


@router.get("/{account_id}", response_model=AccountSummary)
def read_account(account_id: int, session: DbSession, user: CurrentUser, base: BaseCurrency) -> AccountSummary:
    account = get_owned_account(session, user, account_id)
    return _summaries(session, user.id, base, [account.id], include_archived=True)[0]


@router.patch("/{account_id}", response_model=AccountSummary)
def update_account(
    account_id: int, payload: AccountUpdate, session: DbSession, user: CurrentUser, base: BaseCurrency
) -> AccountSummary:
    account = get_owned_account(session, user, account_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(account, field, value)
    if account.account_type is not AccountType.TBSZ:
        account.tbsz_year = None
    elif account.tbsz_year is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A TBSZ account needs its vintage year (tbsz_year).")
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that name already exists.") from exc
    return _summaries(session, user.id, base, [account.id], include_archived=True)[0]


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    session: DbSession,
    user: CurrentUser,
    confirm: Annotated[str, Query(description="The account's exact name, as a guard against accidents")],
) -> Response:
    """Permanently delete an account with all its transactions, import history and sync credentials."""
    account = get_owned_account(session, user, account_id)
    if confirm.strip() != account.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type the account's name exactly to confirm.")
    scope = (Transaction.account_id == account.id, Transaction.user_id == user.id)
    session.execute(delete(Transaction).where(*scope))
    session.execute(delete(ImportLog).where(ImportLog.account_id == account.id, ImportLog.user_id == user.id))
    session.execute(
        delete(BrokerCredential).where(BrokerCredential.account_id == account.id, BrokerCredential.user_id == user.id)
    )
    session.delete(account)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
