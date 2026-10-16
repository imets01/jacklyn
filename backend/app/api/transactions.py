import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.enums import TransactionType
from app.schemas.api import TransactionPage
from app.services.transactions import TransactionFilter, transaction_page

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
