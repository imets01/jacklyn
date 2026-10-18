from fastapi import APIRouter

from app.api import (
    accounts,
    admin,
    assets,
    auth,
    health,
    imports,
    mappings,
    market,
    me,
    portfolio,
    sync,
    transactions,
)

api_router = APIRouter()
for module in (auth, admin, me, health, assets, portfolio, accounts, imports, mappings, market, sync, transactions):
    api_router.include_router(module.router)

__all__ = ["api_router"]
