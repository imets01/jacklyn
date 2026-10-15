from typing import Annotated

from fastapi import APIRouter, Query

from app.api.accounts import account_out
from app.api.deps import CurrentUser, DbSession
from app.schemas import (
    AccountSummaryOut,
    BaseCurrency,
    BucketOut,
    HoldingOut,
    PerformanceOut,
    PerformancePointOut,
    PortfolioSummaryOut,
)
from app.services import portfolio as svc

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

BaseQuery = Annotated[BaseCurrency | None, Query(description="Defaults to the user's base")]


@router.get("/summary", response_model=PortfolioSummaryOut)
def portfolio_summary(
    db: DbSession, user: CurrentUser, base_currency: BaseQuery = None
) -> PortfolioSummaryOut:
    base = base_currency or user.base_currency
    s = svc.summarize(svc.load_portfolio(db, user.id), base)

    def buckets(items: list[svc.Bucket]) -> list[BucketOut]:
        return [BucketOut.model_validate(b) for b in items]

    return PortfolioSummaryOut(
        base_currency=s.base_currency,
        as_of=s.as_of,
        net_worth=s.net_worth,
        invested=s.invested,
        cash=s.cash,
        net_contributions=s.net_contributions,
        total_gain=s.total_gain,
        total_gain_pct=s.total_gain_pct,
        allocation={
            "asset_class": buckets(s.by_asset_class),
            "currency": buckets(s.by_currency),
            "account": buckets(s.by_account),
        },
        accounts=[
            AccountSummaryOut(
                account=account_out(v.account),
                value=v.value,
                invested=v.invested,
                cash=v.cash,
                net_contributions=v.contributions,
                gain=v.value - v.contributions,
                value_in_account_currency=v.value_in_account_currency,
                holdings_count=v.holdings_count,
                cash_by_currency=v.cash_by_currency,
                weight=v.weight,
            )
            for v in s.accounts
        ],
        holdings=[
            HoldingOut(
                asset_id=h.asset.id,
                symbol=h.asset.symbol,
                name=h.asset.name,
                isin=h.asset.isin,
                asset_class=h.asset.asset_class,
                currency=h.asset.currency,
                quantity=h.quantity,
                price=h.price,
                value=h.value,
                cost=h.cost,
                unrealized_gain=h.value - h.cost,
                weight=h.weight,
            )
            for h in s.holdings
        ],
        fx_rates=s.fx_rates,
        fx_source="static",
        warnings=s.warnings,
    )


@router.get("/performance", response_model=PerformanceOut)
def portfolio_performance(
    db: DbSession,
    user: CurrentUser,
    base_currency: BaseQuery = None,
    range: svc.PerformanceRange = svc.PerformanceRange.ONE_YEAR,
) -> PerformanceOut:
    base = base_currency or user.base_currency
    p = svc.performance(svc.load_portfolio(db, user.id), base, range)
    return PerformanceOut(
        base_currency=p.base_currency,
        range=p.range.value,
        points=[PerformancePointOut.model_validate(pt) for pt in p.points],
        start_value=p.start_value,
        end_value=p.end_value,
        change=p.change,
        gain=p.gain,
        gain_pct=p.gain_pct,
    )
