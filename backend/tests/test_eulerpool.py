from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import Session

from app.enums import AssetClass
from app.health.config import load_benchmark
from app.health.exposure import UNCLASSIFIED, PositionInput, build_exposure, overlaps
from app.models import Asset
from app.services import asset_info
from app.services.eulerpool import (
    FundLookThrough,
    fetch_company_country,
    fetch_fund,
    normalize_country,
    parse_countries,
    parse_holdings,
)

D = Decimal


def test_country_names_are_normalized() -> None:
    assert normalize_country("United Kingdom of Great Britain and Northern Ireland") == "United Kingdom"
    assert normalize_country("Korea (the Republic of)") == "South Korea"
    assert normalize_country("Netherlands (the)") == "Netherlands"
    assert normalize_country("Switzerland") == "Switzerland"
    assert normalize_country("Korea") == "South Korea"


def test_parse_countries_converts_percent_and_rejects_incomplete_data() -> None:
    parsed = parse_countries(
        [
            {"symbol": "X", "country": "United States", "exposure": 97.59},
            {"symbol": "X", "country": "United Kingdom of Great Britain and Northern Ireland", "exposure": 0.41},
            {"symbol": "X", "country": "Other", "exposure": 2},
            {"symbol": "X", "country": "Nowhere", "exposure": "n/a"},
        ]
    )
    assert parsed is not None
    assert parsed["United States"] == D("0.9759")
    assert parsed["United Kingdom"] == D("0.0041")
    assert sum(parsed.values()) == 1
    assert parse_countries([{"country": "United States", "exposure": 40}]) is None  # covers too little
    assert parse_countries({"error": "Countries not found"}) is None


def test_parse_holdings_keys_by_isin_and_keeps_the_largest() -> None:
    parsed = parse_holdings(
        [
            {"symbol": "NVDA", "isin": "US67066G1040", "percent": 5.5},
            {"symbol": "CASH", "isin": "", "percent": 0.2},
            {"symbol": "BAD", "isin": "X", "percent": -1},
        ]
    )
    assert parsed == {"US67066G1040": D("0.055"), "CASH": D("0.002")}


def test_fetch_fund_uses_a_bearer_header_and_tolerates_missing_parts() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "countries" in request.url.path:
            return httpx.Response(200, json=[{"country": "Japan", "exposure": 100}])
        return httpx.Response(404, json={"error": "Holdings not found"})

    result = fetch_fund("IE00B4L5YX21", "secret", transport=httpx.MockTransport(handler))
    assert result == FundLookThrough({"Japan": D(1)}, None)
    assert all(r.headers["authorization"] == "Bearer secret" for r in seen)
    assert all("secret" not in str(r.url) for r in seen)  # the key never travels in the URL
    assert fetch_fund("not-an-isin", "secret", transport=httpx.MockTransport(handler)).countries is None


def test_refresh_profile_stores_look_through_only_with_a_key(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(isin: str, token: str) -> FundLookThrough:
        calls.append(isin)
        return FundLookThrough({"Japan": D(1)}, {"JP3633400001": D("0.04")})

    monkeypatch.setattr("app.services.eulerpool.fetch_fund", fake_fetch)
    fund = Asset(symbol="IJPA", currency="EUR", isin="IE00B4L5YX21", asset_class=AssetClass.ETF)
    db.add(fund)
    db.flush()
    profile = asset_info.refresh_profile(db, fund, use_network=False)
    assert profile.country_weights is None
    assert calls == []
    profile = asset_info.refresh_profile(db, fund, use_network=True, eulerpool_token="key")
    assert profile.country_weights == {"Japan": "1.000000"}
    assert profile.holdings == {"JP3633400001": "0.040000"}
    assert calls == ["IE00B4L5YX21"]


def fund(symbol: str, value: str, **extra: object) -> PositionInput:
    return PositionInput(
        asset_id=hash(symbol) % 10_000,
        symbol=symbol,
        name=str(extra.pop("name", symbol)),
        asset_class=AssetClass.ETF,
        currency="EUR",
        value=D(value),
        value_local=D(value),
        price=D(100),
        quantity=D(1),
        **extra,  # type: ignore[arg-type]
    )


def test_reported_countries_replace_index_estimates() -> None:
    europe = fund(
        "MEUD",
        "1000",
        name="Amundi Core Stoxx Europe 600 UCITS ETF",
        country_weights={"United Kingdom": D("0.6"), "Switzerland": D("0.3"), "Other": D("0.1")},
    )
    world = fund("VWCE", "1000", name="Vanguard FTSE All-World UCITS ETF")  # no provider data: estimated
    exposure = build_exposure([europe, world], {}, load_benchmark())
    assert exposure.countries["United Kingdom"] > D(600)
    assert exposure.countries[UNCLASSIFIED] == D(100)  # the provider's "Other" isn't guessed
    assert "Europe (broad, not split)" not in exposure.countries
    assert exposure.country_quality == {"reported": D(1000), "estimated": D(1000)}
    country_notes = [note for note in exposure.notes if "countries" in note]
    assert country_notes == ["VWCE: countries approximated from its index (Global index (spread like MSCI ACWI))"]


def test_overlap_is_exact_with_full_holdings() -> None:
    a = fund("A", "1", holdings={"US1": D("0.06"), "US2": D("0.94")}, top_holdings={"X": D("0.5")})
    b = fund("B", "1", holdings={"US1": D("0.05"), "US3": D("0.95")}, top_holdings={"X": D("0.5")})
    partial = fund("P", "1", holdings={"US1": D("0.05")})
    c = fund("C", "1", top_holdings={"X": D("0.2")})
    found = {(o.first, o.second): (o.shared, o.complete) for o in overlaps([a, b, c])}
    assert found[("A", "B")] == (D("0.05"), True)
    assert found[("A", "C")] == (D("0.2"), False)  # C has no full holdings: top-10 lower bound
    assert overlaps([a, partial])[0].complete is False  # a holdings list covering 5% of the fund isn't exact


def test_company_country_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "Richter Gedeon", "country": "HU"})

    assert fetch_company_country("HU0000123096", "k", transport=httpx.MockTransport(handler)) == "Hungary"
    assert fetch_company_country("bad", "k", transport=httpx.MockTransport(handler)) is None
