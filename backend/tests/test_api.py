from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Account, Institution, Transaction, TransactionType, User
from app.services.fx import default_fx
from tests.conftest import fixture_bytes


def account_id(client, name: str) -> int:
    return int(next(a["id"] for a in client.get("/api/accounts").json() if a["name"] == name))


def upload(client, endpoint: str, name: str, account: int, **form):
    return client.post(
        f"/api/import/{endpoint}",
        files={"file": (name, fixture_bytes(name), "text/csv")},
        data={"account_id": str(account), **form},
    )


def test_seeded_accounts_and_subtypes(client) -> None:
    accounts = {a["name"]: a for a in client.get("/api/accounts").json()}
    assert set(accounts) == {"IBKR Swiss", "IBKR TBSZ 2025", "Lightyear", "Erste NetBroker"}
    assert accounts["IBKR Swiss"]["account_type"] == "swiss"
    tbsz = accounts["IBKR TBSZ 2025"]
    assert tbsz["account_type"] == "tbsz" and tbsz["tbsz_year"] == 2025
    assert tbsz["tbsz"]["maturity_date"] == "2030-12-31"
    assert all(a["transaction_count"] > 0 for a in accounts.values())


def test_summary_is_consistent_across_base_currencies(client) -> None:
    summaries = {
        ccy: client.get("/api/portfolio/summary", params={"base_currency": ccy}).json()
        for ccy in ("CHF", "EUR", "HUF", "USD")
    }
    chf = summaries["CHF"]
    net_worth = Decimal(chf["net_worth"])
    assert net_worth > 0
    assert net_worth == Decimal(chf["invested"]) + Decimal(chf["cash"])
    assert {b["key"] for b in chf["allocation"]["currency"]} == {"CHF", "EUR", "HUF", "USD"}
    assert sum(Decimal(b["weight"]) for b in chf["allocation"]["asset_class"]) == pytest.approx(
        Decimal("1"), abs=Decimal("0.001")
    )
    eur_from_chf = default_fx.convert(net_worth, "CHF", "EUR")
    assert abs(Decimal(summaries["EUR"]["net_worth"]) - eur_from_chf) < Decimal("0.05")
    # money travels as strings, never JSON floats
    assert isinstance(chf["net_worth"], str)


def test_performance_series(client) -> None:
    perf = client.get(
        "/api/portfolio/performance", params={"range": "ALL", "base_currency": "EUR"}
    ).json()
    assert len(perf["points"]) > 20
    summary = client.get("/api/portfolio/summary", params={"base_currency": "EUR"}).json()
    assert Decimal(perf["end_value"]) == pytest.approx(Decimal(summary["net_worth"]), abs=1)


def test_create_account_validates_tbsz_year(client) -> None:
    bad = client.post(
        "/api/accounts",
        json={
            "name": "TBSZ",
            "institution": "erste",
            "account_type": "tbsz",
            "base_currency": "HUF",
        },
    )
    assert bad.status_code == 422
    ok = client.post(
        "/api/accounts",
        json={
            "name": "Erste TBSZ 2026",
            "institution": "erste",
            "account_type": "tbsz",
            "tbsz_year": 2026,
            "base_currency": "huf",
        },
    )
    assert ok.status_code == 201
    assert ok.json()["base_currency"] == "HUF" and ok.json()["tbsz"]["phase"] == "collecting"
    dup = client.post(
        "/api/accounts",
        json={
            "name": "Erste TBSZ 2026",
            "institution": "erste",
            "account_type": "tbsz",
            "tbsz_year": 2026,
            "base_currency": "HUF",
        },
    )
    assert dup.status_code == 409


def test_import_preview_commit_is_idempotent(client) -> None:
    acct = account_id(client, "IBKR Swiss")
    preview = upload(client, "preview", "ibkr_activity.csv", acct).json()
    assert preview["parser_key"] == "ibkr" and not preview["needs_mapping"]
    assert preview["counts"]["new"] == preview["counts"]["total"] > 0
    assert preview["counts"]["error"] == 0

    commit = upload(
        client, "commit", "ibkr_activity.csv", acct, expected_sha256=preview["file_sha256"]
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["rows_imported"] == preview["counts"]["new"]

    again = upload(client, "preview", "ibkr_activity.csv", acct).json()
    assert again["counts"]["new"] == 0
    assert again["counts"]["duplicate"] == preview["counts"]["total"]
    second = upload(client, "commit", "ibkr_activity.csv", acct).json()
    assert second["rows_imported"] == 0

    logs = client.get("/api/import/logs").json()
    assert len(logs) == 2 and logs[0]["parser_key"] == "ibkr"


def test_import_warns_on_institution_mismatch(client) -> None:
    acct = account_id(client, "Erste NetBroker")
    preview = upload(client, "preview", "lightyear_statement.csv", acct).json()
    assert any("LIGHTYEAR" in w for w in preview["warnings"])
    assert preview["is_stub"] is True


def test_generic_mapping_flow_and_saved_mapping_autodetect(client) -> None:
    acct = account_id(client, "Lightyear")
    first = upload(client, "preview", "custom_broker.csv", acct).json()
    assert first["needs_mapping"] and first["suggestion"]["columns"]

    mapping = {
        "columns": {
            "trade_date": "When",
            "type": "What",
            "symbol": "Paper",
            "quantity": "Units",
            "price": "Unit price",
            "amount": "Total",
            "currency": "Cur",
            "external_id": "Ref",
        },
        "date_format": "%d.%m.%Y",
        "decimal_separator": ",",
    }
    import json

    commit = upload(
        client,
        "commit",
        "custom_broker.csv",
        acct,
        mapping=json.dumps(mapping),
        save_mapping_as="My bank",
    )
    assert commit.status_code == 201, commit.text
    assert commit.json()["rows_imported"] == 3 and commit.json()["mapping_id"]

    # Same layout is now recognised automatically via the saved mapping.
    again = upload(client, "preview", "custom_broker.csv", acct).json()
    assert again["mapping_id"] == commit.json()["mapping_id"]
    assert again["counts"]["duplicate"] == 3


def test_invalid_mapping_is_422(client) -> None:
    acct = account_id(client, "Lightyear")
    r = upload(client, "preview", "custom_broker.csv", acct, mapping='{"columns": {}}')
    assert r.status_code == 422 and "trade_date" in r.json()["detail"]


def test_tenant_isolation(client, db) -> None:
    other = User(email="other@example.com", display_name="Other", base_currency="EUR")
    db.add(other)
    db.flush()
    foreign = Account(
        user_id=other.id, name="Secret", institution=Institution.OTHER, base_currency="EUR"
    )
    db.add(foreign)
    db.commit()

    assert client.get(f"/api/accounts/{foreign.id}").status_code == 404
    assert "Secret" not in {a["name"] for a in client.get("/api/accounts").json()}
    assert upload(client, "preview", "ibkr_activity.csv", foreign.id).status_code == 404

    # The composite FK stops a row claiming one user while pointing at another's account.
    me = client.get("/api/me").json()
    db.add(
        Transaction(
            user_id=me["id"],
            account_id=foreign.id,
            type=TransactionType.DEPOSIT,
            trade_date=__import__("datetime").date(2026, 1, 1),
            amount=Decimal("1"),
            currency="EUR",
            fingerprint="x",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
