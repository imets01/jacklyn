"""IBKR Flex sync: fetch one statement, route each IBKR account to its linked Jacklyn account, ingest.

Runs happen in background threads (IBKR takes seconds to minutes to generate a statement): on demand from
the "Sync now" button, and once a day for connections with auto-sync on. Every run records its outcome on
the BrokerCredential so the UI can show it; the shared ingestion pipeline makes overlapping runs harmless.
"""

import datetime as dt
import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx
from defusedxml import ElementTree
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.enums import ImportSource
from app.models import Account, BrokerCredential
from app.models._common import utcnow
from app.parsers.ibkr import IBKRFlexXMLParser
from app.parsers.source import SourceFile
from app.services.ingestion import ingest_transactions
from app.services.sync.ibkr_flex import NOT_FLEX, FlexError, IBKRFlexClient

logger = logging.getLogger(__name__)

IBKR_FLEX = "ibkr_flex"
AUTO_SYNC_EVERY = dt.timedelta(hours=24)
FIRST_CHECK_SECONDS = 60.0  # after startup, so a server restarted every night still syncs
CHECK_EVERY_SECONDS = 3600.0


def _failed(credential: BrokerCredential, message: str) -> None:
    credential.last_status = "failed"
    credential.last_message = message[:2000]


def run_sync(session: Session, credential: BrokerCredential, *, http: httpx.Client | None = None) -> int:
    """One sync run; returns how many transactions it imported.

    Never raises for IBKR or network problems; they end up in `last_status`/`last_message`.
    """
    credential.last_attempt_at = utcnow()
    try:
        content = IBKRFlexClient(credential.token, credential.query_id or "").fetch_statement(http)
        statements = IBKRFlexXMLParser().run_per_account(SourceFile("ibkr-flex.xml", content))
    except FlexError as exc:
        _failed(credential, str(exc))
        session.commit()
        return 0
    except httpx.HTTPError as exc:
        _failed(credential, f"Couldn't reach IBKR ({type(exc).__name__}). Try again later.")
        session.commit()
        return 0
    except ElementTree.ParseError:
        _failed(credential, NOT_FLEX)
        session.commit()
        return 0

    linked: dict[str, Account] = {}
    for candidate in session.scalars(
        select(Account)
        .where(Account.user_id == credential.user_id, Account.external_account_id.in_(statements))
        .order_by(Account.is_archived, Account.id)
    ):
        linked.setdefault(candidate.external_account_id or "", candidate)

    results: list[dict[str, Any]] = []
    for number, parsed in sorted(statements.items()):
        account = linked.get(number)
        entry: dict[str, Any] = {
            "account": number,
            "account_id": account.id if account else None,
            "received": len(parsed.transactions),
            "imported": 0,
            "duplicates": 0,
            "errors": len(parsed.errors),
        }
        if account is not None and parsed.transactions:
            outcome = ingest_transactions(
                session,
                user_id=credential.user_id,
                account_id=account.id,
                transactions=parsed.transactions,
                source=ImportSource.API_SYNC,
                parser_key=parsed.parser_key,
                message=f"{len(parsed.errors)} rows could not be read" if parsed.errors else None,
            )
            entry.update(imported=outcome.imported, duplicates=outcome.duplicates)
        results.append(entry)

    unlinked = [entry["account"] for entry in results if entry["account_id"] is None]
    unreadable = sum(entry["errors"] for entry in results)
    notes = []
    if not results:
        notes.append("The statement contained no accounts. Check that the Flex query includes them.")
    if unlinked:
        notes.append(f"Not linked to a Jacklyn account yet: {', '.join(unlinked)}.")
    if unreadable:
        notes.append(f"{unreadable} rows could not be read.")
    credential.last_status = "partial" if notes else "ok"
    credential.last_message = " ".join(notes) or None
    credential.last_result = results
    credential.last_synced_at = credential.last_attempt_at
    session.commit()
    return sum(int(entry["imported"]) for entry in results)


def sync_is_due(credential: BrokerCredential, now: dt.datetime) -> bool:
    return credential.auto_sync and (
        credential.last_attempt_at is None or now - credential.last_attempt_at >= AUTO_SYNC_EVERY
    )


class SyncService:
    """Starts sync runs in the background, at most one at a time per connection, plus the daily auto-sync."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        transport: httpx.BaseTransport | None = None,
        on_imported: Callable[[], None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._transport = transport
        self._on_imported = on_imported  # e.g. price the new holdings right away
        self._running: set[int] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def is_running(self, credential_id: int) -> bool:
        with self._lock:
            return credential_id in self._running

    def start(self, credential_id: int) -> bool:
        """Begin a run unless one is already going; returns whether a new run started."""
        with self._lock:
            if credential_id in self._running:
                return False
            self._running.add(credential_id)
        self._spawn(lambda: self._run(credential_id))
        return True

    def start_due(self, now: dt.datetime | None = None) -> list[int]:
        now = now or utcnow()
        with self._session_factory() as session:
            credentials = session.scalars(select(BrokerCredential).where(BrokerCredential.provider == IBKR_FLEX))
            due = [credential.id for credential in credentials if sync_is_due(credential, now)]
        return [credential_id for credential_id in due if self.start(credential_id)]

    def start_scheduler(self) -> None:
        threading.Thread(target=self._schedule, name="broker-sync-scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _schedule(self) -> None:
        wait = FIRST_CHECK_SECONDS
        while not self._stop.wait(wait):
            wait = CHECK_EVERY_SECONDS
            try:
                self.start_due()
            except Exception:
                logger.exception("Auto-sync check failed")

    def _spawn(self, target: Callable[[], None]) -> None:
        threading.Thread(target=target, name="broker-sync", daemon=True).start()

    def _run(self, credential_id: int) -> None:
        try:
            with self._session_factory() as session, self._client() as http:
                credential = session.get(BrokerCredential, credential_id)
                imported = run_sync(session, credential, http=http) if credential is not None else 0
            if imported and self._on_imported is not None:
                self._on_imported()
        except Exception:
            logger.exception("IBKR sync %s failed", credential_id)
            with self._session_factory() as session:
                credential = session.get(BrokerCredential, credential_id)
                if credential is not None:
                    _failed(credential, "The sync failed unexpectedly; see the server log.")
                    session.commit()
        finally:
            with self._lock:
                self._running.discard(credential_id)

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=30, headers={"User-Agent": "Jacklyn/1.0"}, transport=self._transport)
