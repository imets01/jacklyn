from fastapi import APIRouter

from app.api import accounts, admin, assets, auth, imports, mappings, market, me, portfolio, transactions

api_router = APIRouter()
for module in (auth, admin, me, assets, portfolio, accounts, imports, mappings, market, transactions):
    api_router.include_router(module.router)

__all__ = ["api_router"]
