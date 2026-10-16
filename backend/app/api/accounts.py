from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import BaseCurrency, CurrentUser, DbSession, get_owned_account
from app.enums import AccountType
from app.models import Account, Asset, BrokerCredential, ImportLog, Transaction
from app.schemas.api import AccountCreate, AccountUpdate, TransactionOut, TransactionPage
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


@router.get("/{account_id}/transactions", response_model=TransactionPage)
def list_transactions(
    account_id: int,
    session: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    account = get_owned_account(session, user, account_id)
    scope = (Transaction.user_id == user.id, Transaction.account_id == account.id)
    total = session.scalar(select(func.count()).select_from(Transaction).where(*scope)) or 0
    rows = session.execute(
        select(Transaction, Asset)
        .outerjoin(Asset, Asset.id == Transaction.asset_id)
        .where(*scope)
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return TransactionPage(
        total=total,
        items=[
            TransactionOut(
                id=tx.id,
                account_id=tx.account_id,
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
            )
            for tx, asset in rows
        ],
    )
