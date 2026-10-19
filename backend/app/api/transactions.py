import datetime as dt
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, MarketService, get_owned_account
from app.enums import ImportSource, TransactionType
from app.schemas.api import (
    AssetOption,
    ManualTransactionsIn,
    ManualTransactionsResult,
    TransactionEdit,
    TransactionPage,
)
from app.services.ingestion import find_duplicates, ingest_transactions
from app.services.transactions import (
    TransactionFilter,
    TransactionNotFoundError,
    asset_options,
    delete_transaction,
    edit_transaction,
    transaction_page,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage)
def search_transactions(
    session: DbSession,
    user: CurrentUser,
    account_ids: Annotated[list[int] | None, Query(alias="account_id")] = None,
    types: Annotated[list[TransactionType] | None, Query(alias="type")] = None,
    asset_id: int | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    """All of the user's transactions, newest first, narrowed by any combination of filters."""
    flt = TransactionFilter(
        account_ids=account_ids, types=types, asset_id=asset_id, search=q, date_from=date_from, date_to=date_to
    )
    return transaction_page(session, user.id, flt, limit, offset)


@router.get("/assets", response_model=list[AssetOption])
def suggest_assets(
    session: DbSession, user: CurrentUser, q: Annotated[str | None, Query(max_length=100)] = None
) -> list[AssetOption]:
    """Assets the user already trades, for picking one when entering a transaction by hand."""
    return asset_options(session, user.id, q)


@router.post("", response_model=ManualTransactionsResult, status_code=status.HTTP_201_CREATED)
def add_transactions(
    payload: ManualTransactionsIn, session: DbSession, user: CurrentUser, market: MarketService
) -> ManualTransactionsResult:
    """Record transactions entered by hand. An identical one already on the account needs `allow_duplicate`."""
    get_owned_account(session, user, payload.account_id)
    if not payload.allow_duplicate and any(
        find_duplicates(session, payload.account_id, payload.transactions, include_deleted=False)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "duplicate", "message": "An identical transaction is already recorded on this account."},
        )
    outcome = ingest_transactions(
        session,
        user_id=user.id,
        account_id=payload.account_id,
        transactions=payload.transactions,
        source=ImportSource.MANUAL,
        keep_duplicates=True,
    )
    market.holdings_changed()
    return ManualTransactionsResult(ids=outcome.transaction_ids)


@router.put("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_transaction(
    transaction_id: int, payload: TransactionEdit, session: DbSession, user: CurrentUser, market: MarketService
) -> None:
    get_owned_account(session, user, payload.account_id)
    try:
        edit_transaction(session, user.id, transaction_id, payload.account_id, payload.transaction)
    except TransactionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    market.holdings_changed()


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_transaction(transaction_id: int, session: DbSession, user: CurrentUser, market: MarketService) -> None:
    """Delete a transaction. A broker row stays deleted when its statement is imported or synced again."""
    try:
        delete_transaction(session, user.id, transaction_id)
    except TransactionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    market.holdings_changed()
