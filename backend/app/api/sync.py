"""IBKR Flex Web Service connection: store the read-only token, sync now, daily auto-sync."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, SyncSvc
from app.models import Account, BrokerCredential, User
from app.schemas.sync import IbkrConnectionIn, IbkrConnectionOut, SyncedAccount
from app.services.sync import IBKR_FLEX
from app.services.sync.service import AUTO_SYNC_EVERY

router = APIRouter(prefix="/api/sync/ibkr", tags=["sync"])


def _credential(session: DbSession, user: User) -> BrokerCredential | None:
    return session.scalar(
        select(BrokerCredential).where(BrokerCredential.user_id == user.id, BrokerCredential.provider == IBKR_FLEX)
    )


def _out(session: DbSession, credential: BrokerCredential, sync: SyncSvc) -> IbkrConnectionOut:
    entries = credential.last_result or []
    numbers = [str(entry["account"]) for entry in entries]
    # Linked live, not as of the last run: an account linked since then shows up right away.
    linked: dict[str, Account] = {}
    for candidate in session.scalars(
        select(Account)
        .where(Account.user_id == credential.user_id, Account.external_account_id.in_(numbers))
        .order_by(Account.is_archived, Account.id)
    ):
        linked.setdefault(candidate.external_account_id or "", candidate)
    last = credential.last_attempt_at
    return IbkrConnectionOut(
        query_id=credential.query_id or "",
        token_hint=f"…{credential.token[-4:]}",
        auto_sync=credential.auto_sync,
        running=sync.is_running(credential.id),
        last_synced_at=credential.last_synced_at,
        last_attempt_at=last,
        next_auto_sync_at=(last + AUTO_SYNC_EVERY if last else None) if credential.auto_sync else None,
        last_status=credential.last_status,  # type: ignore[arg-type]
        last_message=credential.last_message,
        accounts=[
            SyncedAccount(
                account=str(entry["account"]),
                account_id=account.id if (account := linked.get(str(entry["account"]))) else None,
                account_name=account.name if account else None,
                received=int(entry.get("received", 0)),
                imported=int(entry.get("imported", 0)),
                duplicates=int(entry.get("duplicates", 0)),
                errors=int(entry.get("errors", 0)),
            )
            for entry in entries
        ],
    )


@router.get("", response_model=IbkrConnectionOut | None)
def read_connection(session: DbSession, user: CurrentUser, sync: SyncSvc) -> IbkrConnectionOut | None:
    credential = _credential(session, user)
    return _out(session, credential, sync) if credential else None


@router.put("", response_model=IbkrConnectionOut)
def save_connection(
    payload: IbkrConnectionIn, session: DbSession, user: CurrentUser, sync: SyncSvc
) -> IbkrConnectionOut:
    credential = _credential(session, user)
    if credential is None:
        if not payload.token:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter your Flex token.")
        credential = BrokerCredential(user_id=user.id, provider=IBKR_FLEX, token=payload.token)
        session.add(credential)
    elif payload.token:
        credential.token = payload.token
    if payload.token or credential.query_id != payload.query_id:
        credential.last_status = credential.last_message = None  # an old error no longer applies
    credential.query_id = payload.query_id
    credential.auto_sync = payload.auto_sync
    session.commit()
    return _out(session, credential, sync)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(session: DbSession, user: CurrentUser) -> Response:
    """Forget the token. Transactions already synced stay."""
    credential = _credential(session, user)
    if credential is not None:
        session.delete(credential)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run", response_model=IbkrConnectionOut, status_code=status.HTTP_202_ACCEPTED)
def run_now(session: DbSession, user: CurrentUser, sync: SyncSvc) -> IbkrConnectionOut:
    """Start a sync in the background; poll GET until `running` is false."""
    credential = _credential(session, user)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connect IBKR first.")
    sync.start(credential.id)
    session.expire_all()  # a fast run may already have finished
    return _out(session, credential, sync)
