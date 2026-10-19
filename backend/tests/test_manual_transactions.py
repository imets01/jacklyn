"""Transactions entered, corrected and deleted by hand, and how they meet later imports of the same statement."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

BUY = {"date": "2025-02-03", "type": "buy", "symbol": "ZZMAN", "quantity": "3", "unit_price": "20", "currency": "EUR"}
STATEMENT = [
    {"date": "2025-01-02", "type": "deposit", "amount": "1000", "currency": "EUR"},
    {**BUY, "fee": "1", "external_id": "T-1"},
    {"date": "2025-03-01", "type": "dividend", "symbol": "ZZMAN", "amount": "4", "currency": "EUR"},
]


def _account(client: TestClient, name: str) -> int:
    response = client.post("/api/accounts", json={"name": name, "broker": "Manual Broker", "currency": "EUR"})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _ledger(client: TestClient, account_id: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = client.get("/api/transactions", params={"account_id": account_id}).json()["items"]
    return items


def _import(client: TestClient, account_id: int, rows: list[dict[str, str]] = STATEMENT) -> dict[str, int]:
    response = client.post(
        "/api/import/commit", json={"account_id": account_id, "transactions": rows, "filename": "statement.csv"}
    )
    assert response.status_code == 200, response.text
    result: dict[str, int] = response.json()
    return result


def _add(client: TestClient, account_id: int, *rows: dict[str, str], allow_duplicate: bool = False) -> Any:
    return client.post(
        "/api/transactions",
        json={"account_id": account_id, "transactions": list(rows), "allow_duplicate": allow_duplicate},
    )


def test_add_by_hand_and_confirm_a_second_identical_one(client: TestClient) -> None:
    account = _account(client, "Manual add")
    created = _add(client, account, BUY)
    assert created.status_code == 201, created.text
    [row] = _ledger(client, account)
    assert row["id"] == created.json()["ids"][0]
    assert (row["manual"], row["symbol"], Decimal(row["amount"])) == (True, "ZZMAN", Decimal(60))
    assert not any(log["source"] == "manual" for log in client.get("/api/import/logs").json())

    again = _add(client, account, BUY)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "duplicate"
    assert _add(client, account, BUY, allow_duplicate=True).status_code == 201
    holdings = client.get("/api/portfolio/holdings", params={"account_id": account}).json()["holdings"]
    assert Decimal(holdings[0]["quantity"]) == 6

    # A statement with the same trade once: the first manual entry stands for it, the second stays extra.
    assert _import(client, account, [BUY])["imported"] == 0


def test_currency_exchange_is_two_legs(client: TestClient) -> None:
    account = _account(client, "Manual FX")
    legs = [
        {"date": "2025-04-01", "type": "fx_conversion", "amount": "-100", "currency": "CHF"},
        {"date": "2025-04-01", "type": "fx_conversion", "amount": "106.5", "currency": "EUR"},
    ]
    assert _add(client, account, *legs).status_code == 201
    amounts = {row["currency"]: Decimal(row["amount"]) for row in _ledger(client, account)}
    assert amounts == {"CHF": Decimal(-100), "EUR": Decimal("106.5")}
    too_many = _add(client, account, *legs, legs[0])
    assert too_many.status_code == 422


def test_a_corrected_import_stays_corrected(client: TestClient) -> None:
    account = _account(client, "Manual edit")
    _import(client, account)
    buy = next(row for row in _ledger(client, account) if row["type"] == "buy")
    assert buy["manual"] is False

    fixed = {**BUY, "quantity": "4", "unit_price": "19.5", "fee": "1"}
    response = client.put(f"/api/transactions/{buy['id']}", json={"account_id": account, "transaction": fixed})
    assert response.status_code == 204, response.text
    edited = next(row for row in _ledger(client, account) if row["id"] == buy["id"])
    assert (Decimal(edited["quantity"]), Decimal(edited["amount"]), edited["external_id"]) == (
        Decimal(4),
        Decimal(78),
        "T-1",
    )

    assert _import(client, account)["imported"] == 0  # the original row is recognized, the correction kept
    assert Decimal(next(row for row in _ledger(client, account) if row["type"] == "buy")["quantity"]) == 4

    invalid = client.put(
        f"/api/transactions/{buy['id']}", json={"account_id": account, "transaction": {**BUY, "quantity": "0"}}
    )
    assert invalid.status_code == 422


def test_deleted_broker_rows_stay_deleted(client: TestClient) -> None:
    account = _account(client, "Manual delete")
    _import(client, account)
    dividend = next(row for row in _ledger(client, account) if row["type"] == "dividend")
    assert client.delete(f"/api/transactions/{dividend['id']}").status_code == 204
    assert len(_ledger(client, account)) == 2

    assert _import(client, account)["imported"] == 0  # re-import: not brought back

    # Entered by hand on purpose, the same dividend is not refused.
    assert _add(client, account, STATEMENT[2]).status_code == 201
    # A manual entry leaves nothing behind when deleted: adding it again isn't a duplicate.
    manual = next(row for row in _ledger(client, account) if row["manual"])
    assert client.delete(f"/api/transactions/{manual['id']}").status_code == 204
    assert _add(client, account, STATEMENT[2]).status_code == 201


def test_moving_to_another_account(client: TestClient) -> None:
    source, target = _account(client, "Manual move from"), _account(client, "Manual move to")
    _import(client, source)
    _import(client, target)
    buy = next(row for row in _ledger(client, source) if row["type"] == "buy")
    values = {**BUY, "fee": "1", "external_id": "T-1"}
    moved = client.put(f"/api/transactions/{buy['id']}", json={"account_id": target, "transaction": values})
    assert moved.status_code == 204, moved.text
    assert [row["type"] for row in _ledger(client, target)].count("buy") == 2
    assert _import(client, source)["imported"] == 0  # the old account doesn't get it back


def test_other_people_cannot_touch_it(client: TestClient, make_user: Callable[..., TestClient]) -> None:
    account = _account(client, "Manual private")
    _add(client, account, BUY)
    [row] = _ledger(client, account)
    assert any(option["symbol"] == "ZZMAN" for option in client.get("/api/transactions/assets?q=zzm").json())

    friend = make_user()
    friend_account = _account(friend, "Friend's")
    assert friend.delete(f"/api/transactions/{row['id']}").status_code == 404
    edit = {"account_id": friend_account, "transaction": BUY}
    assert friend.put(f"/api/transactions/{row['id']}", json=edit).status_code == 404
    assert _add(friend, account, BUY).status_code == 404
    assert friend.get("/api/transactions/assets", params={"q": "zzm"}).json() == []
    assert len(_ledger(client, account)) == 1
