from fastapi import APIRouter

from app.api import accounts, imports, mappings, market, me, portfolio

api_router = APIRouter()
for module in (me, portfolio, accounts, imports, mappings, market):
    api_router.include_router(module.router)

__all__ = ["api_router"]
