"""Broker API sync (IBKR Flex Web Service) request/response models. The token is write-only."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class IbkrConnectionIn(BaseModel):
    # Optional on update: leaving it out keeps the stored token.
    token: str | None = Field(default=None, min_length=8, max_length=128, pattern=r"^\S+$")
    query_id: str = Field(pattern=r"^\d{1,20}$")
    auto_sync: bool = True


class SyncedAccount(BaseModel):
    account: str  # IBKR account number, e.g. U1234567
    account_id: int | None  # the Jacklyn account it is linked to, if any
    account_name: str | None
    received: int
    imported: int
    duplicates: int
    errors: int


class IbkrConnectionOut(BaseModel):
    query_id: str
    token_hint: str  # last characters only
    auto_sync: bool
    running: bool
    last_synced_at: dt.datetime | None
    last_attempt_at: dt.datetime | None
    next_auto_sync_at: dt.datetime | None
    last_status: Literal["ok", "partial", "failed"] | None
    last_message: str | None
    accounts: list[SyncedAccount]
