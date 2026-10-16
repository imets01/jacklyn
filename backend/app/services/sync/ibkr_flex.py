"""IBKR Flex Web Service client (read-only Flex token + Query ID).

Flow: SendRequest returns a reference code, then GetStatement is polled until the statement
is generated. The XML goes through the same IBKRFlexXMLParser as a manual upload and then into
the shared ingestion pipeline, so API syncs dedupe against file imports.
"""

import time
from dataclasses import dataclass

import httpx
from defusedxml import ElementTree
from sqlalchemy.orm import Session

from app.enums import ImportSource
from app.parsers.base import ParseResult
from app.parsers.ibkr import IBKRFlexXMLParser
from app.parsers.source import SourceFile
from app.services.ingestion import IngestOutcome, ingest_transactions

FLEX_BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
FLEX_VERSION = "3"
# 1019: statement generation in progress; 1018: too many requests. Both are worth retrying.
RETRYABLE_CODES = {"1018", "1019"}


class FlexError(RuntimeError):
    pass


@dataclass
class IBKRFlexClient:
    token: str
    query_id: str
    base_url: str = FLEX_BASE_URL
    poll_interval_seconds: float = 3.0
    max_attempts: int = 10
    timeout_seconds: float = 30.0

    def fetch_statement(self, http: httpx.Client | None = None) -> bytes:
        client = http or httpx.Client(timeout=self.timeout_seconds, headers={"User-Agent": "Jacklyn/0.1"})
        try:
            response = client.get(
                f"{self.base_url}/SendRequest", params={"t": self.token, "q": self.query_id, "v": FLEX_VERSION}
            )
            response.raise_for_status()
            reference, statement_url = self._parse_send_response(response.content)
            for attempt in range(self.max_attempts):
                statement = client.get(statement_url, params={"t": self.token, "q": reference, "v": FLEX_VERSION})
                statement.raise_for_status()
                if b"<FlexQueryResponse" in statement.content[:2000]:
                    return statement.content
                code, message = self._parse_status(statement.content)
                if code not in RETRYABLE_CODES:
                    raise FlexError(f"IBKR Flex error {code}: {message}")
                if attempt < self.max_attempts - 1:
                    time.sleep(self.poll_interval_seconds)
            raise FlexError("IBKR did not finish generating the statement in time; try again shortly.")
        finally:
            if http is None:
                client.close()

    def fetch(self, http: httpx.Client | None = None) -> ParseResult:
        content = self.fetch_statement(http)
        return IBKRFlexXMLParser().run(SourceFile("ibkr-flex.xml", content))

    @staticmethod
    def _parse_send_response(content: bytes) -> tuple[str, str]:
        root = ElementTree.fromstring(content)
        if (root.findtext("Status") or "").strip() != "Success":
            code = (root.findtext("ErrorCode") or "?").strip()
            raise FlexError(f"IBKR Flex error {code}: {(root.findtext('ErrorMessage') or '').strip()}")
        reference = (root.findtext("ReferenceCode") or "").strip()
        url = (root.findtext("Url") or "").strip()
        if not reference or not url:
            raise FlexError("IBKR Flex response is missing the reference code or URL.")
        return reference, url

    @staticmethod
    def _parse_status(content: bytes) -> tuple[str, str]:
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise FlexError("Unexpected response from IBKR Flex Web Service.") from exc
        return (root.findtext("ErrorCode") or "").strip(), (root.findtext("ErrorMessage") or "").strip()


def sync_ibkr_account(
    session: Session, *, user_id: int, account_id: int, client: IBKRFlexClient, http: httpx.Client | None = None
) -> tuple[ParseResult, IngestOutcome]:
    result = client.fetch(http)
    outcome = ingest_transactions(
        session,
        user_id=user_id,
        account_id=account_id,
        transactions=result.transactions,
        source=ImportSource.API_SYNC,
        parser_key=result.parser_key,
        message=f"{len(result.errors)} rows could not be parsed" if result.errors else None,
    )
    return result, outcome
