from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import BaseCurrency, CurrentUser, DbSession
from app.health.service import build_report
from app.models import InvestorProfile
from app.schemas.health import HealthReport, InvestorProfileIn, InvestorProfileOut

router = APIRouter(prefix="/api/health", tags=["health"])


@router.put("/profile", response_model=InvestorProfileOut)
def save_profile(payload: InvestorProfileIn, session: DbSession, user: CurrentUser) -> InvestorProfile:
    profile = session.get(InvestorProfile, user.id) or InvestorProfile(user_id=user.id)
    data = payload.model_dump()
    overrides = data.pop("target_overrides")
    for field, value in data.items():
        setattr(profile, field, value)
    # Stored as strings: JSON has no decimal type, and floats never touch the allocation math.
    profile.target_overrides = {k: str(v) for k, v in overrides.items() if v} if overrides else None
    session.add(profile)
    session.commit()
    return profile


@router.get("/report", response_model=HealthReport)
def health_report(
    session: DbSession,
    user: CurrentUser,
    base: BaseCurrency,
    amount: Annotated[Decimal | None, Query(ge=0, le=10_000_000)] = None,
    include_cash: bool = False,
) -> HealthReport:
    """Breakdowns, rule findings with sources, score and a contribution-only rebalancing plan."""
    return build_report(session, user_id=user.id, base_currency=base, amount=amount, include_idle_cash=include_cash)
