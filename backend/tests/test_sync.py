"""IBKR Flex sync: per-account routing, idempotent re-runs, status reporting and the write-only token."""

import datetime as dt
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import BrokerCredential
from app.parsers.ibkr import IBKRFlexXMLParser
from app.parsers.source import SourceFile
from app.services.sync import SyncService
from app.services.sync.service import AUTO_SYNC_EVERY, sync_is_due
from tests.conftest import fixture_bytes

TOKEN = "123456789012345678901234"
SECOND_ACCOUNT = """
    <FlexStatement accountId="U7654321" fromDate="20250101" toDate="20250331">
      <AccountInformation accountId="U7654321" currency="EUR" />
      <CashTransactions>
        <CashTransaction accountId="U7654321" currency="EUR" description="CASH RECEIPTS" dateTime="20250110"
          amount="2500" type="Deposits/Withdrawals" transactionID="8001" levelOfDetail="DETAIL" />
      </CashTransactions>
    </FlexStatement>
  </FlexStatements>"""
TWO_ACCOUNTS = fixture_bytes("ibkr_flex.xml").decode().replace("</FlexStatements>", SECOND_ACCOUNT).encode()
SEND_OK = (
    b"<FlexStatementResponse><Status>Success</Status><ReferenceCode>42</ReferenceCode>"
    b"<Url>https://flex.test/GetStatement</Url></FlexStatementResponse>"
)


class FakeIbkr:
    """IBKR's two-step Flex Web Service: SendRequest -> reference code, GetStatement -> the XML."""

    def __init__(self) -> None:
        self.statement = TWO_ACCOUNTS
        self.send_response = SEND_OK
        self.tokens: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.tokens.append(request.url.params.get("t", ""))
        if request.url.path.endswith("/SendRequest"):
            return httpx.Response(200, content=self.send_response)
        return httpx.Response(200, content=self.statement)


class InlineSync(SyncService):
    """Runs syncs on the calling thread, so a test sees the outcome right after POST /run."""

    def _spawn(self, target: Callable[[], None]) -> None:
        target()


@pytest.fixture
def ibkr(monkeypatch: pytest.MonkeyPatch) -> FakeIbkr:
    fake = FakeIbkr()
    monkeypatch.setattr(app.state, "sync", InlineSync(SessionLocal, transport=httpx.MockTransport(fake)))
    return fake


def test_flex_statement_splits_per_account() -> None:
    source = SourceFile("flex.xml", TWO_ACCOUNTS)
    per_account = IBKRFlexXMLParser().run_per_account(source)
    assert sorted(per_account) == ["U1234567", "U7654321"]
    assert len(per_account["U7654321"].transactions) == 1
    assert per_account["U7654321"].account_hint is not None
    assert per_account["U7654321"].account_hint.currency == "EUR"
    # A manual upload still reads every account into the one account it is imported to.
    merged = IBKRFlexXMLParser().run(source)
    assert len(merged.transactions) == sum(len(result.transactions) for result in per_account.values())


def test_sync_routes_accounts_and_is_idempotent(ibkr: FakeIbkr, make_user: Callable[..., TestClient]) -> None:
    owner = make_user()
    swiss = owner.post(
        "/api/accounts",
        json={"name": "IBKR", "broker": "Interactive Brokers", "currency": "CHF", "external_account_id": "U1234567"},
    ).json()
    assert owner.get("/api/sync/ibkr").json() is None
    assert owner.post("/api/sync/ibkr/run").status_code == 404
    assert owner.put("/api/sync/ibkr", json={"query_id": "987654"}).status_code == 422  # token needed first

    saved = owner.put("/api/sync/ibkr", json={"token": TOKEN, "query_id": "987654"})
    assert saved.status_code == 200, saved.text
    assert TOKEN not in saved.text  # write-only
    assert saved.json()["token_hint"] == f"…{TOKEN[-4:]}"

    first = owner.post("/api/sync/ibkr/run")
    assert first.status_code == 202
    status = first.json()
    assert (status["running"], status["last_status"]) == (False, "partial")
    assert "U7654321" in status["last_message"]
    rows = {row["account"]: row for row in status["accounts"]}
    assert rows["U1234567"]["account_id"] == swiss["id"]
    assert rows["U1234567"]["imported"] == rows["U1234567"]["received"] > 0
    assert rows["U7654321"] == {
        "account": "U7654321",
        "account_id": None,
        "account_name": None,
        "received": 1,
        "imported": 0,
        "duplicates": 0,
        "errors": 0,
    }
    assert set(ibkr.tokens) == {TOKEN}

    # Linking the second IBKR account shows up at once; the next run fills it, and nothing is imported twice.
    euro = owner.post(
        "/api/accounts",
        json={
            "name": "IBKR EUR",
            "broker": "Interactive Brokers",
            "currency": "EUR",
            "external_account_id": "U7654321",
        },
    ).json()
    linked = {row["account"]: row for row in owner.get("/api/sync/ibkr").json()["accounts"]}
    assert linked["U7654321"]["account_name"] == "IBKR EUR"
    again = owner.post("/api/sync/ibkr/run").json()
    assert (again["last_status"], again["last_message"]) == ("ok", None)
    rows = {row["account"]: row for row in again["accounts"]}
    assert rows["U1234567"]["imported"] == 0
    assert rows["U1234567"]["duplicates"] == rows["U1234567"]["received"]
    assert rows["U7654321"]["imported"] == 1
    assert owner.get("/api/transactions", params={"account_id": euro["id"]}).json()["total"] == 1
    logs = owner.get("/api/import/logs").json()
    assert {log["source"] for log in logs} == {"api_sync"}

    # Connections are per user.
    stranger = make_user()
    assert stranger.get("/api/sync/ibkr").json() is None
    assert stranger.post("/api/sync/ibkr/run").status_code == 404

    # Disconnecting forgets the token but keeps what was synced.
    assert owner.delete("/api/sync/ibkr").status_code == 204
    assert owner.get("/api/sync/ibkr").json() is None
    assert owner.get("/api/transactions", params={"account_id": swiss["id"]}).json()["total"] > 0


def test_ibkr_errors_are_reported(ibkr: FakeIbkr, make_user: Callable[..., TestClient]) -> None:
    owner = make_user()
    owner.put("/api/sync/ibkr", json={"token": TOKEN, "query_id": "1", "auto_sync": False})
    ibkr.send_response = (
        b"<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode>"
        b"<ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>"
    )
    status = owner.post("/api/sync/ibkr/run").json()
    assert status["last_status"] == "failed"
    assert status["last_message"] == "IBKR Flex error 1012: Token has expired."
    assert status["last_synced_at"] is None
    assert status["next_auto_sync_at"] is None  # auto-sync is off

    ibkr.send_response = b"<html>maintenance</html>"
    assert "isn't a Flex statement" in owner.post("/api/sync/ibkr/run").json()["last_message"]

    # A new token clears the old error.
    cleared = owner.put("/api/sync/ibkr", json={"token": "9" * 24, "query_id": "1"}).json()
    assert (cleared["last_status"], cleared["last_message"], cleared["auto_sync"]) == (None, None, True)


def test_auto_sync_is_due_once_a_day() -> None:
    now = dt.datetime(2026, 10, 18, 6, tzinfo=dt.UTC)
    credential = BrokerCredential(auto_sync=True, last_attempt_at=None)
    assert sync_is_due(credential, now)
    credential.last_attempt_at = now - AUTO_SYNC_EVERY + dt.timedelta(minutes=5)
    assert not sync_is_due(credential, now)
    credential.last_attempt_at = now - AUTO_SYNC_EVERY
    assert sync_is_due(credential, now)
    credential.auto_sync = False
    assert not sync_is_due(credential, now)
