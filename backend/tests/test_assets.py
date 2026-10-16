import datetime as dt
import struct
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.enums import AssetClass, ImportSource, PriceSource, TransactionType
from app.models import Account, Asset, AssetLogo, AssetPrice, AssetProfile, User
from app.schemas.standard import StandardTransaction
from app.services import charts
from app.services.asset_info import (
    apply_info,
    commodity_key,
    detect_provider,
    is_commodity,
    logo_candidates,
    refresh_logos,
    refresh_profile,
    resolve_logos,
    safe_svg,
    usable_logo,
    website_domain,
)
from app.services.ingestion import ingest_transactions
from app.services.portfolio import PortfolioEngine

T = TransactionType


def png(width: int = 128, height: int = 128) -> bytes:
    """Just enough of a PNG for type and size sniffing."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


# ------------------------------------------------------------------------------ classification


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (("BlackRock Asset Management Ireland - ETF", None), "iShares"),
        ((None, "iShs VII-Core S&P 500 U.ETF"), "iShares"),
        ((None, "Vanguard FTSE All-World UCITS ETF"), "Vanguard"),
        ((None, "Xtrackers MSCI World Swap UCITS ETF"), "Xtrackers"),
        (("Amundi Luxembourg S.A.", None), "Amundi"),
        ((None, "Lyxor Core STOXX Europe 600"), "Amundi"),
        ((None, "SPDR S&P 500 UCITS ETF"), "SPDR"),
        ((None, "Apple Inc."), None),
    ],
)
def test_detect_provider(texts: tuple[str | None, str | None], expected: str | None) -> None:
    provider = detect_provider(*texts)
    assert (provider.name if provider else None) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("iShares Physical Gold ETC", True),
        ("Xtrackers Physical Silver ETC", True),
        ("Xetra-Gold", True),
        ("WisdomTree Physical Precious Metals", True),
        ("Barrick Gold Corp", False),
        ("Gold Fields Ltd", False),
        (None, False),
    ],
)
def test_is_commodity(name: str | None, expected: bool) -> None:
    assert is_commodity(name) is expected


def test_website_domain() -> None:
    assert website_domain("https://www.apple.com") == "apple.com"
    assert website_domain("nvidia.com/en-us") == "nvidia.com"
    assert website_domain("javascript:alert(1)") is None
    assert website_domain("http://10.0.0.1/admin") is None
    assert website_domain("http://intranet/") is None
    assert website_domain(None) is None


def test_apply_info_fills_names_classes_and_logo_keys() -> None:
    etf = Asset(symbol="QDVE", currency="EUR", isin="IE00B3WJKG14", asset_class=AssetClass.STOCK)
    etf_profile = AssetProfile()
    apply_info(
        etf,
        etf_profile,
        {
            "quoteType": "ETF",
            "longName": "iShares S&P 500 Information Technology Sector UCITS ETF USD (Acc)",
            "fundFamily": "BlackRock Asset Management Ireland - ETF",
            "netExpenseRatio": 0.15,
            "totalAssets": 20611657728,
        },
    )
    assert etf.asset_class is AssetClass.ETF
    assert etf.name == "iShares S&P 500 Information Technology Sector UCITS ETF USD (Acc)"
    assert (etf_profile.provider, etf_profile.expense_ratio) == ("iShares", Decimal("0.0015"))
    assert logo_candidates(etf, etf_profile) == ["isin:IE00B3WJKG14", "domain:ishares.com"]

    gold = Asset(symbol="PPFB", currency="EUR", asset_class=AssetClass.STOCK)
    gold_profile = AssetProfile()
    apply_info(gold, gold_profile, {"quoteType": "EQUITY", "longName": "iShares Physical Gold ETC"})
    assert gold.asset_class is AssetClass.COMMODITY
    assert gold_profile.provider == "iShares"
    assert logo_candidates(gold, gold_profile) == ["commodity:gold"]

    stock = Asset(symbol="AAPL", currency="USD", name="Apple Inc.", asset_class=AssetClass.STOCK)
    stock_profile = AssetProfile()
    apply_info(
        stock,
        stock_profile,
        {"quoteType": "EQUITY", "longName": "Apple Inc.", "sector": "Technology", "website": "https://www.apple.com"},
    )
    assert stock.asset_class is AssetClass.STOCK
    assert stock_profile.sector == "Technology"
    assert logo_candidates(stock, stock_profile) == ["symbol:AAPL", "domain:apple.com"]

    share = Asset(symbol="RICHTER", currency="HUF", name="Richter Gedeon Nyrt.", asset_class=AssetClass.STOCK)
    apply_info(share, AssetProfile(), {"quoteType": "MUTUALFUND", "longName": "Gedeon Richter Plc"})
    assert share.asset_class is AssetClass.STOCK  # Yahoo mislabels some Budapest shares

    fund = Asset(symbol="ERSTEBOND", currency="HUF", asset_class=AssetClass.STOCK)
    apply_info(fund, AssetProfile(), {"quoteType": "MUTUALFUND", "longName": "Erste Bond Dollar Alap"})
    assert fund.asset_class is AssetClass.FUND

    coin = Asset(symbol="BTC", currency="USD", yf_ticker="BTC-USD", asset_class=AssetClass.STOCK)
    coin_profile = AssetProfile()
    apply_info(coin, coin_profile, {"quoteType": "CRYPTOCURRENCY", "longName": "Bitcoin USD"})
    assert coin.asset_class is AssetClass.CRYPTO
    assert logo_candidates(coin, coin_profile) == ["crypto:btc"]


def test_refresh_profile_without_network_uses_the_name(db: Session) -> None:
    asset = Asset(symbol="VWCE", currency="EUR", name="Vanguard FTSE All-World UCITS ETF (Acc)")
    db.add(asset)
    db.flush()
    profile = refresh_profile(db, asset, use_network=False)
    assert asset.asset_class is AssetClass.ETF
    assert profile.provider == "Vanguard"
    assert logo_candidates(asset, profile) == ["domain:vanguard.com"]


# ------------------------------------------------------------------------------ logos


def test_usable_logo_accepts_rasters_only() -> None:
    assert usable_logo(png()) == "image/png"
    assert usable_logo(png(16, 16)) is None  # too small to look good
    assert usable_logo(b"\x00\x00\x01\x00" + b"\x00" * 50) == "image/x-icon"
    assert usable_logo(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>") is None
    assert usable_logo(b"<html>not found</html>") is None
    assert usable_logo(png() + b"\x00" * 300_000) is None


def _transport(responses: dict[str, httpx.Response], seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        for marker, response in responses.items():
            if marker in str(request.url):
                return response
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_refresh_logos_stores_hits_and_misses_once(db: Session) -> None:
    seen: list[str] = []
    transport = _transport({"domain=ishares.com": httpx.Response(200, content=png())}, seen)
    stored = refresh_logos(db, {"domain:ishares.com", "domain:unknown.example"}, None, transport=transport)
    assert stored == 1
    logos = {logo.key: logo for logo in db.scalars(select(AssetLogo))}
    assert logos["domain:ishares.com"].content_type == "image/png"
    assert logos["domain:ishares.com"].source == "google"
    assert logos["domain:unknown.example"].data is None  # a recorded miss

    seen.clear()
    assert refresh_logos(db, {"domain:ishares.com", "domain:unknown.example"}, None, transport=transport) == 0
    assert seen == []  # nothing is due yet


def test_refresh_logos_prefers_logo_dev_with_a_token_and_keeps_old_images(db: Session) -> None:
    seen: list[str] = []
    transport = _transport({"img.logo.dev/apple.com": httpx.Response(200, content=png(256, 256))}, seen)
    assert refresh_logos(db, {"domain:apple.com"}, "pk_test", transport=transport) == 1
    assert "img.logo.dev/apple.com" in seen[0]
    logo = db.get(AssetLogo, "domain:apple.com")
    assert logo is not None
    assert logo.source == "logo.dev"

    # Due again, but every source fails: the old image stays.
    logo.fetched_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=365)
    db.flush()
    assert refresh_logos(db, {"domain:apple.com"}, None, transport=_transport({}, [])) == 0
    assert db.get(AssetLogo, "domain:apple.com").data == png(256, 256)  # type: ignore[union-attr]


def test_crypto_logos_fall_back_to_the_icon_set(db: Session) -> None:
    seen: list[str] = []
    transport = _transport({"cryptocurrency-icons": httpx.Response(200, content=png())}, seen)
    assert refresh_logos(db, {"crypto:btc"}, None, transport=transport) == 1
    assert seen == [
        "https://api.elbstream.com/logos/crypto/btc",
        "https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/128/color/btc.png",
    ]


SAFE_SVG = (
    b'<svg width="60" height="60" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">'
    b'<defs><clipPath id="c"><rect width="60" height="60"/></clipPath></defs>'
    b'<g clip-path="url(#c)"><rect width="60" height="60" fill="black"/><path d="M1 1h2v2z" fill="#fff"/></g></svg>'
)


@pytest.mark.parametrize(
    ("svg", "ok"),
    [
        (SAFE_SVG, True),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', False),
        (b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect/></svg>', False),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.example/x.png"/></svg>', False),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://evil.example/p)"/></svg>', False),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div/></foreignObject></svg>', False),
        (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>', False),
        (b"<html><body>not an svg</body></html>", False),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><filter id="b"><feGaussianBlur stdDeviation="2"/></filter>'
            b'<rect filter="url(#b)" style="opacity:.5"/></svg>',
            True,
        ),
    ],
)
def test_svg_logos_must_be_plain_drawings(svg: bytes, ok: bool) -> None:
    assert safe_svg(svg) is ok
    assert usable_logo(svg) == ("image/svg+xml" if ok else None)


def test_resolve_logos_prefers_elbstream_and_falls_back_by_website(db: Session) -> None:
    seen: list[str] = []
    transport = _transport(
        {
            "isin/IE00B3WJKG14": httpx.Response(200, content=SAFE_SVG),
            "domain=apple.com": httpx.Response(200, content=png()),
        },
        seen,
    )
    candidates = {1: ["isin:IE00B3WJKG14", "domain:ishares.com"], 2: ["isin:US0378331005", "domain:apple.com"], 3: []}
    chosen, stored = resolve_logos(db, candidates, None, transport=transport)
    assert chosen == {1: "isin:IE00B3WJKG14", 2: "domain:apple.com", 3: None}
    assert stored == 2
    assert not any("ishares.com" in url for url in seen)  # the ISIN hit made the website icon unnecessary

    seen.clear()
    assert resolve_logos(db, candidates, None, transport=transport)[0] == chosen
    assert seen == []  # cached hits and recorded misses aren't fetched again


def test_commodity_and_currency_tiles_come_from_elbstream(db: Session) -> None:
    seen: list[str] = []
    transport = _transport({"elbstream": httpx.Response(200, content=png())}, seen)
    assert refresh_logos(db, {"commodity:gold", "currency:EUR"}, None, transport=transport) == 2
    assert sorted(seen) == [
        "https://api.elbstream.com/logos/commodity/gold?size=128",
        "https://api.elbstream.com/logos/currency/EUR",
    ]
    assert commodity_key("Xtrackers IE Physical Silver ETC") == "silver"
    assert commodity_key("WisdomTree Brent Crude Oil") == "oil"
    assert commodity_key("Apple Inc.") is None


# ------------------------------------------------------------------------------ holding detail (engine)


def test_holding_detail_combines_accounts_with_average_cost(db: Session, user: User, account: Account) -> None:
    second = Account(user_id=user.id, name="Second", broker="Lightyear", currency="EUR")
    db.add(second)
    db.flush()

    def tx(day: int, tx_type: TransactionType, **fields: object) -> StandardTransaction:
        return StandardTransaction.model_validate(
            {"date": dt.date(2025, 1, day), "type": tx_type, "currency": "EUR", "symbol": "SXR8", **fields}
        )

    ingest_transactions(
        db,
        user_id=user.id,
        account_id=account.id,
        source=ImportSource.MANUAL,
        transactions=[
            tx(2, T.BUY, quantity="2", unit_price="100", fee="1"),
            tx(3, T.BUY, quantity="1", unit_price="130"),
            tx(4, T.SELL, quantity="1", unit_price="140"),
        ],
    )
    ingest_transactions(
        db,
        user_id=user.id,
        account_id=second.id,
        source=ImportSource.MANUAL,
        transactions=[tx(5, T.BUY, quantity="1", unit_price="120")],
    )
    asset = db.scalars(select(Asset).where(Asset.symbol == "SXR8")).one()
    for day, close in [(5, "150"), (6, "160")]:
        db.add(
            AssetPrice(
                asset_id=asset.id, price_date=dt.date(2025, 1, day), close=Decimal(close), source=PriceSource.SEED
            )
        )
    db.commit()

    engine = PortfolioEngine(db, user_id=user.id, base_currency="EUR", as_of=dt.date(2025, 1, 6))
    detail = engine.holding_detail(asset.id)
    assert detail is not None
    # Account 1 keeps 2 shares at (201 + 130) / 3 = 110.333...; account 2 has 1 at 120.
    assert detail.quantity == Decimal(3)
    assert detail.avg_cost == Decimal("113.555556")
    assert detail.value == Decimal("480.00")
    assert (detail.price, detail.previous_close, detail.price_change_pct) == (
        Decimal(160),
        Decimal(150),
        Decimal("0.0667"),
    )
    assert [a.account_name for a in detail.accounts] == ["Test IBKR", "Second"]
    assert [a.type for a in detail.activity] == [T.BUY, T.SELL, T.BUY, T.BUY]
    holdings = engine.holdings().holdings
    assert {h.account_name: h.avg_cost for h in holdings} == {
        "Test IBKR": Decimal("110.333333"),
        "Second": Decimal("120.000000"),
    }
    assert engine.holding_detail(asset.id + 999) is None


# ------------------------------------------------------------------------------ charts


def test_yahoo_chart_parses_downsamples_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    index = pd.date_range("2016-01-01", periods=2000, freq="D", tz="Europe/Berlin")

    def fake_history(ticker: str, range_key: str) -> pd.DataFrame:
        calls.append((ticker, range_key))
        return pd.DataFrame({"Close": [float(i + 1) for i in range(len(index))]}, index=index)

    monkeypatch.setattr(charts, "_history", fake_history)
    charts.chart_cache.clear()
    points = charts.yahoo_chart("QDVE.DE", "MAX")
    assert len(points) == charts.MAX_POINTS
    assert points[-1].close == Decimal(2000)
    assert points[0].time.tzinfo is not None
    assert charts.yahoo_chart("QDVE.DE", "MAX") is points
    assert calls == [("QDVE.DE", "MAX")]
    charts.chart_cache.clear()


# ------------------------------------------------------------------------------ API


def _a_holding(client: TestClient) -> dict[str, Any]:
    holdings = client.get("/api/portfolio/holdings", params={"base": "CHF"}).json()["holdings"]
    return max(holdings, key=lambda h: Decimal(h["value"]))


def test_holding_detail_and_chart_endpoints(client: TestClient) -> None:
    holding = _a_holding(client)
    detail = client.get(f"/api/portfolio/holdings/{holding['asset_id']}", params={"base": "CHF"})
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["asset"]["symbol"] == holding["symbol"]
    assert Decimal(body["quantity"]) >= Decimal(holding["quantity"])
    assert body["accounts"]
    assert body["activity"]
    assert client.get("/api/portfolio/holdings/999999").status_code == 404

    chart = client.get(f"/api/assets/{holding['asset_id']}/chart", params={"range": "1Y"})
    assert chart.status_code == 200
    payload = chart.json()
    assert payload["source"] == "stored"  # live data is off in tests
    assert len(payload["points"]) > 100
    assert client.get(f"/api/assets/{holding['asset_id']}/chart", params={"range": "2Y"}).status_code == 422


def test_logo_endpoint_is_cached_and_scoped(client: TestClient, make_user: Callable[..., TestClient]) -> None:
    holding = _a_holding(client)
    asset_id = holding["asset_id"]
    assert client.get(f"/api/assets/{asset_id}/logo").status_code == 404
    with SessionLocal() as session:
        session.merge(AssetProfile(asset_id=asset_id, logo_key="domain:test-logo.example"))
        session.merge(AssetLogo(key="domain:test-logo.example", data=png(), content_type="image/png", source="test"))
        session.commit()

    refreshed = next(h for h in client.get("/api/portfolio/holdings").json()["holdings"] if h["asset_id"] == asset_id)
    assert refreshed["logo_url"].startswith(f"/api/assets/{asset_id}/logo?v=")
    logo = client.get(refreshed["logo_url"])
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert "immutable" in logo.headers["cache-control"]
    assert logo.content == png()
    assert client.get("/api/portfolio/summary").headers["cache-control"] == "no-store"

    with SessionLocal() as session:
        session.merge(AssetLogo(key="currency:CHF", data=SAFE_SVG, content_type="image/svg+xml", source="test"))
        session.commit()
    cash = client.get("/api/portfolio/holdings").json()["cash"]
    chf = next(c for c in cash if c["currency"] == "CHF")
    badge = client.get(chf["logo_url"])
    assert (badge.status_code, badge.headers["content-type"]) == (200, "image/svg+xml")
    assert "sandbox" in badge.headers["content-security-policy"]
    assert client.get("/api/currencies/chf/logo").status_code == 422
    assert client.get("/api/currencies/XYZ/logo").status_code == 404

    friend = make_user()
    assert friend.get(f"/api/assets/{asset_id}/logo").status_code == 404
    assert friend.get(f"/api/assets/{asset_id}/chart").status_code == 404
    assert friend.get(f"/api/portfolio/holdings/{asset_id}").status_code == 404
