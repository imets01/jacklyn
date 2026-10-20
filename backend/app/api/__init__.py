from fastapi import APIRouter

from app.api import (
    accounts,
    admin,
    assets,
    auth,
    backups,
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
ROUTERS = (auth, admin, backups, me, health, assets, portfolio, accounts, imports, mappings, market, sync, transactions)
for module in ROUTERS:
    api_router.include_router(module.router)

__all__ = ["api_router"]
