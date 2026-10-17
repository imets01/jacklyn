import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.enums import AssetClass
from app.health.allocation import effective_horizon, glide_path_equity, parse_overrides, suggested_equity
from app.health.config import load_benchmark, load_rules
from app.health.exposure import BENCHMARK_OTHER, UNCLASSIFIED, PositionInput, build_exposure
from app.health.rebalance import (
    Instrument,
    build_orders,
    choose_instrument,
    contribution_split,
    full_rebalance,
    months_to_band,
    plan_contribution,
    within_band,
)
from app.health.rules import METRICS, HealthContext, band, evaluate

D = Decimal
RULES = load_rules()
BENCH = load_benchmark()
ABS, REL = RULES.absolute_band, RULES.relative_band


def position(symbol: str, value: str, asset_class: AssetClass = AssetClass.STOCK, **extra: object) -> PositionInput:
    return PositionInput(
        asset_id=hash(symbol) % 10_000,
        symbol=symbol,
        name=extra.pop("name", symbol),  # type: ignore[arg-type]
        asset_class=asset_class,
        currency=str(extra.pop("currency", "CHF")),
        value=D(value),
        value_local=D(value),
        price=D(100),
        quantity=D(value) / 100,
        **extra,  # type: ignore[arg-type]
    )


def context(positions: list[PositionInput], cash: dict[str, Decimal] | None = None, **extra: object) -> HealthContext:
    defaults: dict[str, object] = {
        "base_currency": "CHF",
        "home_country": "Switzerland",
        "emergency_fund": D(0),
        "targets": None,
        "suggested_equity": None,
        "absolute_band": ABS,
        "relative_band": REL,
    }
    defaults.update(extra)
    return HealthContext(exposure=build_exposure(positions, cash or {}, BENCH), benchmark=BENCH, **defaults)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------- config


def test_every_rule_has_a_metric_and_citations() -> None:
    assert RULES.rules
    for rule in RULES.rules:
        assert rule.metric in METRICS, rule.id
        assert rule.citations, rule.id
        assert all(c.url.startswith("https://") for c in rule.citations)
    assert abs(sum(BENCH.sectors.values(), D(0)) - 1) < D("0.001")
    assert abs(sum(BENCH.countries.values(), D(0)) - 1) < D("0.001")


@pytest.mark.parametrize(
    ("name", "label"),
    [
        ("iShares Core S&P 500 UCITS ETF USD (Acc)", "Broad US index"),
        ("iShares S&P 500 Information Technology Sector UCITS ETF", "US index (narrow)"),
        ("Vanguard FTSE All-World UCITS ETF (Acc)", "Global index (spread like MSCI ACWI)"),
        ("iShares Core SPI ETF (CH)", "Swiss index"),
        ("iShares Core MSCI Japan IMI UCITS ETF", "Japan index"),
        ("Amundi Core Stoxx Europe 600 UCITS ETF Acc", "Europe index (country split not available)"),
    ],
)
def test_index_mapping(name: str, label: str) -> None:
    mapping = BENCH.index_for(name)
    assert mapping is not None
    assert mapping.label == label


# ------------------------------------------------------------------------------------------- allocation


@pytest.mark.parametrize(
    ("horizon", "equity"),
    [(40, "0.90"), (25, "0.90"), (10, "0.66"), (0, "0.50"), (-7, "0.30"), (-30, "0.30")],
)
def test_glide_path_follows_vanguard_shape(horizon: int, equity: str) -> None:
    assert glide_path_equity(horizon, RULES.profile) == D(equity)


def test_risk_tolerance_shifts_and_clamps() -> None:
    assert suggested_equity(30, "balanced", RULES.profile) == D("0.80")
    assert suggested_equity(30, "aggressive", RULES.profile) == D("1.00")
    assert suggested_equity(0, "conservative", RULES.profile) == D("0.30")
    assert effective_horizon(None, 1990, dt.date(2026, 6, 1)) == 29
    assert effective_horizon(12, 1990, dt.date(2026, 6, 1)) == 12
    assert effective_horizon(None, None, dt.date(2026, 6, 1)) is None


def test_target_overrides_are_validated() -> None:
    assert parse_overrides({"equity": "0.7", "bonds": "0.2", "commodities": "0.1"}) == {
        "equity": D("0.7"),
        "bonds": D("0.2"),
        "commodities": D("0.1"),
    }
    with pytest.raises(ValueError, match="100%"):
        parse_overrides({"equity": "0.7", "bonds": "0.2"})
    with pytest.raises(ValueError, match="Unknown"):
        parse_overrides({"real_estate": "1"})


# ------------------------------------------------------------------------------------------- rebalancing


def test_band_uses_the_tighter_of_absolute_and_relative() -> None:
    assert band(D("0.60"), ABS, REL) == D("0.05")  # 25% of 60% is 15 points; 5 is tighter
    assert band(D("0.10"), ABS, REL) == D("0.025")  # 25% of 10% is tighter
    assert band(D(0), ABS, REL) == ABS
    assert not within_band(
        {"equity": D(87), "commodities": D(13)}, {"equity": D("0.9"), "commodities": D("0.1")}, ABS, REL
    )
    assert within_band({"equity": D(88), "commodities": D(12)}, {"equity": D("0.9"), "commodities": D("0.1")}, ABS, REL)


def test_contribution_fills_shortfalls_first_and_spends_everything() -> None:
    values = {"equity": D(9000), "bonds": D(1000)}
    targets = {"equity": D("0.8"), "bonds": D("0.2")}
    # After 1000: total 11000, bonds should be 2200 -> shortfall 1200 > 1000, so all money goes to bonds.
    assert contribution_split(values, targets, D(1000)) == {"bonds": D(1000)}
    # After 5000: total 15000 -> bonds need 2000, equity needs 3000; exactly the amount.
    assert contribution_split(values, targets, D(5000)) == {"equity": D(3000), "bonds": D(2000)}
    # After 10000: total 20000 -> equity needs 7000, bonds 3000. With nothing overweight the shortfalls
    # always add up to exactly the deposit.
    split = contribution_split(values, targets, D(10000))
    assert split == {"equity": D(7000), "bonds": D(3000)}
    assert sum(split.values()) == D(10000)
    # Overweight bonds are never sold: everything goes to equity.
    assert contribution_split({"equity": D(1000), "bonds": D(9000)}, targets, D(500)) == {"equity": D(500)}
    assert contribution_split(values, targets, D(0)) == {}


def test_contribution_split_shares_a_too_small_budget_proportionally() -> None:
    values = {"equity": D(500), "bonds": D(300), "commodities": D(200)}
    targets = {"equity": D("0.5"), "bonds": D("0.3"), "commodities": D("0.2")}
    # Already on target: new money follows the targets.
    assert contribution_split(values, targets, D(100)) == {"equity": D(50), "bonds": D(30), "commodities": D(20)}
    # Equity is overweight; after +100 (total 1100) bonds are 130 short and gold 120 short, together more
    # than the 100 available, so the money is shared in proportion: 52 / 48.
    skewed = {"equity": D(700), "bonds": D(200), "commodities": D(100)}
    assert contribution_split(skewed, targets, D(100)) == {"bonds": D(52), "commodities": D(48)}


def instrument(
    symbol: str, category: str, price: str, value: str = "1000", ter: str | None = "0.002", **extra: object
) -> Instrument:
    return Instrument(
        asset_id=hash(symbol) % 10_000,
        symbol=symbol,
        name=symbol,
        category=category,
        currency=str(extra.get("currency", "CHF")),
        price=D(price),
        local_per_base=D(str(extra.get("local_per_base", "1"))),
        value=D(value),
        ter=D(ter) if ter is not None else None,
    )


def test_cheapest_then_largest_instrument_is_chosen() -> None:
    cheap_small = instrument("CHEAP", "equity", "10", value="100", ter="0.001")
    pricey_big = instrument("PRICEY", "equity", "10", value="9000", ter="0.004")
    unknown = instrument("UNKNOWN", "equity", "10", value="99999", ter=None)
    assert choose_instrument([pricey_big, cheap_small, unknown]) is cheap_small
    twin = instrument("TWIN", "equity", "10", value="5000", ter="0.001")
    assert choose_instrument([cheap_small, twin]) is twin
    assert choose_instrument([]) is None


def test_whole_shares_round_down_and_leftovers_roll_over() -> None:
    funds = [instrument("EQ", "equity", "95"), instrument("BD", "bonds", "40")]
    orders, unspent = build_orders({"equity": D(300), "bonds": D(100)}, funds, fractional=False, min_order=D(0))
    by_symbol = {o.instrument.symbol: o for o in orders if o.instrument}
    assert by_symbol["EQ"].quantity == 3  # 285 spent, 15 rolls to bonds
    assert by_symbol["BD"].quantity == 2  # 100 + 15 = 115 -> 2 x 40
    assert unspent == D("35.00")


def test_fractional_shares_and_currency_conversion() -> None:
    usd = instrument("SPY", "equity", "500", local_per_base="1.25", currency="USD")
    orders, unspent = build_orders({"equity": D(1000)}, [usd], fractional=True, min_order=D(0))
    assert orders[0].quantity == D("2.5")  # CHF 1000 = USD 1250 = 2.5 shares
    assert orders[0].local_amount == D("1250.00")
    assert unspent == 0


def test_minimum_order_and_missing_category() -> None:
    funds = [instrument("EQ", "equity", "10")]
    orders, unspent = build_orders({"equity": D(30)}, funds, fractional=True, min_order=D(50))
    assert orders == []
    assert unspent == D("30.00")
    orders, _ = build_orders({"bonds": D(200)}, funds, fractional=True, min_order=D(0))
    assert orders[0].instrument is None  # nothing held in bonds: the plan names the category, not a product
    assert orders[0].amount == D(200)


def test_months_to_band_and_full_rebalance() -> None:
    targets = {"equity": D("0.8"), "bonds": D("0.2")}
    assert months_to_band({"equity": D(800), "bonds": D(200)}, targets, D(0), ABS, REL) == 0
    # Bonds 5% vs a 20% target (band 5 points): +1000/month all to bonds; need bonds >= 15% of the total.
    values = {"equity": D(9500), "bonds": D(500)}
    months = months_to_band(values, targets, D(1000), ABS, REL)
    assert months == 2  # 10% after one month, 2500/12000 = 20.8% after two
    assert months_to_band(values, targets, D(0), ABS, REL) is None
    moves = full_rebalance(values, targets)
    assert moves == {"equity": D("-1500.00"), "bonds": D("1500.00")}
    assert sum(moves.values()) == 0


def test_plan_contribution_projects_the_result() -> None:
    values = {"equity": D(9500), "bonds": D(500)}
    targets = {"equity": D("0.8"), "bonds": D("0.2")}
    funds = [instrument("EQ", "equity", "100"), instrument("BD", "bonds", "50")]
    plan = plan_contribution(values, targets, D(1000), funds, monthly=D(1000), absolute=ABS, relative=REL)
    assert [(o.instrument.symbol if o.instrument else None, o.amount) for o in plan.orders] == [("BD", D("1000.00"))]
    assert plan.after["bonds"] == D(1500) / D(11000)
    assert not plan.in_band_before
    assert plan.months_to_band == 2


# ------------------------------------------------------------------------------------------- exposure


def test_exposure_looks_through_funds() -> None:
    world = position(
        "VWCE",
        "6000",
        AssetClass.ETF,
        name="Vanguard FTSE All-World UCITS ETF",
        ter=D("0.0022"),
        provider="Vanguard",
        class_weights={"stock": D("0.99"), "cash": D("0.01")},
        sector_weights={"technology": D("0.3"), "financial_services": D("0.7")},
        top_holdings={"AAPL": D("0.05"), "MSFT": D("0.04")},
    )
    spx = position(
        "SXR8",
        "3000",
        AssetClass.ETF,
        name="iShares Core S&P 500 UCITS ETF",
        ter=D("0.0007"),
        provider="iShares",
        top_holdings={"AAPL": D("0.07"), "NVDA": D("0.06")},
    )
    nestle = position("NESN", "1000", country="Switzerland", sector="Consumer Defensive")
    exposure = build_exposure([world, spx, nestle], {"CHF": D(500)}, BENCH)
    assert exposure.total == D(10500)
    assert exposure.categories["equity"] == D(6000) * D("0.99") + D(3000) + D(1000)
    assert exposure.categories["cash"] == D(60) + D(500)
    assert exposure.countries["United States"] == D(3000) + D(5940) * BENCH.countries["United States"]
    assert exposure.countries[BENCHMARK_OTHER] == D(5940) * BENCH.countries["Other"]
    assert exposure.countries["Switzerland"] == D(1000) + D(5940) * BENCH.countries["Switzerland"]
    assert exposure.sectors["Consumer Staples"] == D(1000)
    assert exposure.sectors["Information Technology"] == D(5940) * D("0.3")
    assert exposure.sectors[UNCLASSIFIED] == D(3000)  # SXR8 has no sector data in this test
    assert exposure.broad_fund_value == D(9000)
    assert exposure.ter_cost / exposure.ter_value == (D(6000) * D("0.0022") + D(3000) * D("0.0007")) / D(9000)
    assert [(o.first, o.second, o.shared) for o in exposure.overlaps] == [("VWCE", "SXR8", D("0.05"))]
    assert any("approximated from its index" in note for note in exposure.notes)


# ------------------------------------------------------------------------------------------- rules


def findings_by_rule(ctx: HealthContext) -> dict[str, str]:
    return {f.rule_id: f.severity for f in evaluate(RULES, ctx).findings}


def test_single_stock_concentration_levels_and_messages() -> None:
    ctx = context(
        [
            position("NESN", "1200", name="Nestlé SA", country="Switzerland"),
            position("X", "8800", AssetClass.ETF, name="Vanguard FTSE All-World"),
        ]
    )
    result = evaluate(RULES, ctx)
    finding = next(f for f in result.findings if f.rule_id == "single_stock_concentration")
    assert finding.severity == "problem"
    assert finding.message == "Nestlé SA is 12.0% of your portfolio (limit 10.0%)."
    assert finding.citations[0].publisher.startswith("FINRA")

    fine = context([position("A", "300"), position("B", "9700", AssetClass.ETF, name="Vanguard FTSE All-World")])
    finding = next(f for f in evaluate(RULES, fine).findings if f.rule_id == "single_stock_concentration")
    assert finding.severity == "good"
    assert "No single stock is more than 5.0%" in finding.message


def test_rules_without_data_are_skipped_and_score_is_transparent() -> None:
    funds_only = context([position("W", "10000", AssetClass.ETF, name="Vanguard FTSE All-World", ter=D("0.0022"))])
    result = evaluate(RULES, funds_only)
    assert "single_stock_concentration" in result.skipped  # no single stocks
    assert "allocation_drift" in result.skipped  # no targets without a profile
    assert "fund_fees" in {f.rule_id for f in result.findings}
    assert result.score == RULES.score_start + sum(line.points for line in result.score_lines)

    risky = context([position("A", "6000", country="United States"), position("B", "4000", country="United States")])
    result = evaluate(RULES, risky)
    severities = {f.rule_id: f.severity for f in result.findings}
    assert severities["too_few_holdings"] == "warning"
    assert severities["single_stock_concentration"] == "problem"
    assert result.score == 100 - sum(RULES.penalties[s] for s in severities.values() if s in RULES.penalties)
    assert {line.rule_id for line in result.score_lines} >= {"too_few_holdings", "single_stock_concentration"}


def test_home_bias_fees_and_drift() -> None:
    swiss = context(
        [
            position("CHSPI", "4000", AssetClass.ETF, name="iShares Core SPI ETF (CH)", ter=D("0.001")),
            position("VWCE", "6000", AssetClass.ETF, name="Vanguard FTSE All-World", ter=D("0.0022")),
        ],
        targets={"equity": D("0.6"), "bonds": D("0.4")},
        suggested_equity=D("0.6"),
    )
    severities = findings_by_rule(swiss)
    assert severities["home_bias"] == "warning"  # ~41% Swiss vs 2% of the world
    assert severities["fund_fees"] == "good"  # 0.17% weighted
    assert severities["allocation_drift"] == "warning"  # 100% equity vs 60% target
    assert severities["equity_vs_profile"] == "warning"
    assert severities["broad_core"] == "good"


def test_cash_drag_respects_the_emergency_fund() -> None:
    holdings = [position("VWCE", "8000", AssetClass.ETF, name="Vanguard FTSE All-World")]
    assert findings_by_rule(context(holdings, {"CHF": D(2000)})).get("cash_drag") == "info"
    assert "cash_drag" not in findings_by_rule(context(holdings, {"CHF": D(2000)}, emergency_fund=D(1800)))


# ------------------------------------------------------------------------------------------- API


def test_profile_and_report_api(client: TestClient, make_user: Callable[..., TestClient]) -> None:
    bare = client.get("/api/health/report", params={"base": "CHF"})
    assert bare.status_code == 200, bare.text
    report = bare.json()
    assert report["profile"] is None
    assert report["rebalance"] is None
    assert report["has_holdings"] is True
    assert {"asset_class", "country", "sector", "currency", "issuer"} <= set(report["breakdowns"])
    assert all(f["citations"] for f in report["findings"])
    country_rows = {row["label"]: row["compare"] for row in report["breakdowns"]["country"]["slices"]}
    assert not any("benchmark mix" in label for label in country_rows)  # the source's lump isn't a row
    assert country_rows.get("Other countries (in global funds)") is None  # shown without a comparison
    assert "isn't broken down" in report["breakdowns"]["country"]["note"]

    assert client.put("/api/health/profile", json={"risk_tolerance": "yolo"}).status_code == 422
    bad_targets = {"horizon_years": 20, "target_overrides": {"equity": "0.5", "bonds": "0.2"}}
    assert client.put("/api/health/profile", json=bad_targets).status_code == 422

    saved = client.put(
        "/api/health/profile",
        json={
            "horizon_years": 30,
            "risk_tolerance": "balanced",
            "monthly_contribution": "1000",
            "emergency_fund": "5000",
        },
    )
    assert saved.status_code == 200, saved.text
    report = client.get("/api/health/report", params={"base": "CHF"}).json()
    assert report["suggested_equity"] == "0.80"
    assert report["targets"] == {"equity": "0.80", "bonds": "0.20"}
    assert report["targets_source"] == "profile"
    plan = report["rebalance"]
    assert plan["monthly_contribution"] == "1000.00" or Decimal(plan["monthly_contribution"]) == 1000
    assert Decimal(plan["amount"]) == 1000
    assert sum(Decimal(o["amount"]) for o in plan["orders"]) + Decimal(plan["unspent"]) == Decimal(plan["amount"])

    manual = client.put(
        "/api/health/profile",
        json={"horizon_years": 30, "target_overrides": {"equity": "0.9", "commodities": "0.1"}},
    ).json()
    assert manual["target_overrides"] == {"equity": "0.9", "commodities": "0.1"}
    custom = client.get("/api/health/report", params={"base": "CHF", "amount": "2500", "include_cash": True}).json()
    assert custom["targets_source"] == "manual"
    assert Decimal(custom["rebalance"]["amount"]) >= 2500

    friend = make_user()
    assert friend.get("/api/health/profile").json() is None  # profiles are per user
    assert friend.get("/api/health/report").json()["has_holdings"] is False
