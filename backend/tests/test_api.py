import json
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import fixture_bytes


def _upload(client: TestClient, name: str, content: bytes | None = None, **form: str) -> dict:  # type: ignore[type-arg]
    response = client.post("/api/import/preview", files={"file": (name, content or fixture_bytes(name))}, data=form)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def _create_account(client: TestClient, **fields: object) -> dict:  # type: ignore[type-arg]
    response = client.post("/api/accounts", json={"broker": "Test Broker", "currency": "CHF", **fields})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_health_and_user(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    me = client.get("/api/me").json()
    assert me["base_currency"] == "CHF"


def test_seeded_dashboard(client: TestClient) -> None:
    summary = client.get("/api/portfolio/summary").json()
    names = {a["name"] for a in summary["accounts"]}
    assert {"IBKR Swiss", "IBKR TBSZ 2025", "Lightyear", "Erste NetBroker"} <= names
    assert Decimal(summary["net_worth"]) > 0
    tbsz = next(a for a in summary["accounts"] if a["account_type"] == "tbsz")
    assert tbsz["tbsz_year"] == 2025
    assert tbsz["tbsz_tax_free_from"] == "2031-01-01"
    assert {s["key"] for s in summary["allocations"]["wrapper"]} == {"regular", "tbsz-2025"}
    assert summary["market"]["synthetic_price_assets"] > 0

    huf = client.get("/api/portfolio/summary", params={"base": "HUF"}).json()
    assert huf["base_currency"] == "HUF"
    assert Decimal(huf["net_worth"]) > Decimal(summary["net_worth"]) * 100


def test_history_and_holdings(client: TestClient) -> None:
    for range_key in ("1W", "1M", "3M", "YTD", "1Y", "ALL"):
        history = client.get("/api/portfolio/history", params={"range": range_key}).json()
        assert history["points"], range_key
        assert len(history["points"]) <= 370
    assert client.get("/api/portfolio/history", params={"range": "5Y"}).status_code == 422
    holdings = client.get("/api/portfolio/holdings", params={"account_id": 1}).json()
    assert holdings["holdings"]
    assert {h["account_id"] for h in holdings["holdings"]} == {1}


def test_base_currency_validation(client: TestClient) -> None:
    assert client.get("/api/portfolio/summary", params={"base": "EURO"}).status_code == 422


def test_account_crud_and_tbsz_rules(client: TestClient) -> None:
    bad = client.post(
        "/api/accounts", json={"name": "TBSZ", "broker": "Erste", "currency": "HUF", "account_type": "tbsz"}
    )
    assert bad.status_code == 422
    created = _create_account(client, name="Erste TBSZ 2026", account_type="tbsz", tbsz_year=2026, currency="HUF")
    assert created["tbsz_tax_free_from"] == "2032-01-01"
    duplicate = client.post("/api/accounts", json={"name": "Erste TBSZ 2026", "broker": "x", "currency": "HUF"})
    assert duplicate.status_code == 409
    renamed = client.patch(f"/api/accounts/{created['id']}", json={"name": "TBSZ 2026"}).json()
    assert renamed["name"] == "TBSZ 2026"
    assert client.get("/api/accounts/99999").status_code == 404


def test_account_edit_relabels_currency_without_touching_amounts(client: TestClient) -> None:
    account = _create_account(client, name="Wrong currency", currency="EUR", broker="Lightyear")
    committed = client.post(
        "/api/import/commit",
        json={
            "account_id": account["id"],
            "transactions": [
                {"date": "2025-01-02", "type": "deposit", "amount": "500", "currency": "EUR"},
                {"date": "2025-01-03", "type": "deposit", "amount": "200", "currency": "CHF"},
            ],
            "filename": "x.csv",
        },
    )
    assert committed.json()["imported"] == 2
    before = client.get(f"/api/accounts/{account['id']}").json()

    edited = client.patch(
        f"/api/accounts/{account['id']}",
        json={"currency": "chf", "broker": "Lightyear Europe", "external_account_id": "LY-1", "track_cash": True},
    )
    assert edited.status_code == 200, edited.text
    after = edited.json()
    assert (after["currency"], after["broker"], after["external_account_id"]) == ("CHF", "Lightyear Europe", "LY-1")
    # A label fix, not a conversion: the value in the base currency and every stored amount are unchanged.
    assert after["value"] == before["value"]
    assert after["transaction_count"] == before["transaction_count"]
    stored = client.get(f"/api/accounts/{account['id']}/transactions").json()["items"]
    assert sorted((tx["currency"], Decimal(tx["amount"])) for tx in stored) == [
        ("CHF", Decimal(200)),
        ("EUR", Decimal(500)),
    ]
    holdings = client.get("/api/portfolio/holdings", params={"account_id": account["id"]}).json()
    assert {(c["currency"], Decimal(c["amount"])) for c in holdings["cash"]} == {
        ("CHF", Decimal(200)),
        ("EUR", Decimal(500)),
    }


def test_account_edit_validation(client: TestClient) -> None:
    first = _create_account(client, name="Edit A")
    _create_account(client, name="Edit B")
    url = f"/api/accounts/{first['id']}"
    assert client.patch(url, json={"name": "Edit B"}).status_code == 409
    assert client.patch(url, json={"currency": "EURO"}).status_code == 422
    assert client.patch(url, json={"currency": None}).status_code == 422
    assert client.patch(url, json={"name": ""}).status_code == 422
    assert client.patch(url, json={"account_type": "tbsz"}).status_code == 422  # needs a vintage year
    tbsz = client.patch(url, json={"account_type": "tbsz", "tbsz_year": 2025}).json()
    assert (tbsz["account_type"], tbsz["tbsz_year"]) == ("tbsz", 2025)
    back = client.patch(url, json={"account_type": "standard"}).json()
    assert (back["account_type"], back["tbsz_year"]) == ("standard", None)
    assert client.get(url).json()["name"] == "Edit A"


def test_import_known_broker_preview_commit_and_dedupe(client: TestClient) -> None:
    account = _create_account(client, name="IBKR Import Test", external_account_id="U1234567")
    preview = _upload(client, "ibkr_activity.csv")
    assert preview["status"] == "parsed"
    assert preview["detection"]["parser_key"] == "ibkr_activity_csv"
    assert preview["suggested_account_id"] == account["id"]  # matched by IBKR account number
    assert preview["summary"]["duplicates"] == 0

    payload = {
        "account_id": account["id"],
        "transactions": [row["transaction"] for row in preview["transactions"]],
        "parser_key": preview["detection"]["parser_key"],
        "filename": preview["filename"],
        "file_sha256": preview["file_sha256"],
    }
    first = client.post("/api/import/commit", json=payload).json()
    assert first["imported"] == preview["summary"]["total"]

    again = _upload(client, "ibkr_activity.csv", account_id=str(account["id"]))
    assert again["summary"]["new"] == 0
    assert all(row["duplicate"] for row in again["transactions"])
    second = client.post("/api/import/commit", json=payload).json()
    assert (second["imported"], second["duplicates"]) == (0, first["imported"])

    summary = client.get(f"/api/accounts/{account['id']}").json()
    assert summary["transaction_count"] == first["imported"]
    logs = client.get("/api/import/logs").json()
    assert logs[0]["rows_duplicate"] == first["imported"]


def test_unknown_csv_goes_through_column_mapper_and_saved_preset(client: TestClient) -> None:
    account = _create_account(client, name="Revolut", currency="USD")
    preview = _upload(client, "revolut_trading.csv", account_id=str(account["id"]))
    assert preview["status"] == "needs_mapping"
    table = preview["table"]
    assert table["headers"][:3] == ["Date", "Ticker", "Type"]
    assert len(table["sample_rows"]) == 5

    mapping = table["suggested"]
    mapped = _upload(client, "revolut_trading.csv", account_id=str(account["id"]), mapping=json.dumps(mapping))
    assert mapped["status"] == "parsed"
    assert mapped["summary"]["total"] == 5

    saved = client.post(
        "/api/mappings",
        json={"name": "Revolut Trading CSV", "header_signature": table["header_signature"], "config": mapping},
    )
    assert saved.status_code == 201, saved.text
    auto = _upload(client, "revolut_trading.csv", account_id=str(account["id"]))
    assert auto["status"] == "parsed"
    assert auto["mapping_used"]["name"] == "Revolut Trading CSV"
    forced = _upload(client, "revolut_trading.csv", parser_key="generic")
    assert forced["status"] == "needs_mapping"

    assert any(m["name"] == "Revolut Trading CSV" for m in client.get("/api/mappings").json())
    assert client.delete(f"/api/mappings/{saved.json()['id']}").status_code == 204


def test_unsupported_and_invalid_uploads(client: TestClient) -> None:
    assert _upload(client, "statement.pdf", b"%PDF-1.7 ...")["status"] == "unsupported"
    empty = client.post("/api/import/preview", files={"file": ("empty.csv", b"")})
    assert empty.status_code == 400
    bad_commit = client.post("/api/import/commit", json={"account_id": 1, "transactions": [{"date": "2025-01-01"}]})
    assert bad_commit.status_code == 422


def test_delete_account_removes_its_data_only(client: TestClient) -> None:
    keep = _create_account(client, name="Keep me", currency="EUR")
    doomed = _create_account(client, name="Delete me", currency="EUR")
    for account in (keep, doomed):
        response = client.post(
            "/api/import/commit",
            json={
                "account_id": account["id"],
                "transactions": [{"date": "2025-01-02", "type": "deposit", "amount": "100", "currency": "EUR"}],
                "filename": "x.csv",
            },
        )
        assert response.json()["imported"] == 1

    assert client.delete(f"/api/accounts/{doomed['id']}", params={"confirm": "delete me"}).status_code == 400
    assert client.delete(f"/api/accounts/{doomed['id']}").status_code == 422
    assert client.delete(f"/api/accounts/{doomed['id']}", params={"confirm": "Delete me"}).status_code == 204

    assert client.get(f"/api/accounts/{doomed['id']}").status_code == 404
    assert client.get(f"/api/accounts/{doomed['id']}/transactions").status_code == 404
    assert all(log["account_id"] != doomed["id"] for log in client.get("/api/import/logs").json())
    assert client.get(f"/api/accounts/{keep['id']}").json()["transaction_count"] == 1
    # The name is free again.
    assert client.post("/api/accounts", json={"name": "Delete me", "broker": "X", "currency": "EUR"}).status_code == 201
