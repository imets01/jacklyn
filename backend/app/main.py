import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, imports, portfolio
from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.db import SessionLocal, engine
from app.models import Base
from app.schemas import UserOut
from app.services.seed import run_startup_seed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Phase 1: create tables directly. Alembic migrations take over once the
    # schema needs to evolve with real data in it.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        run_startup_seed(db, get_settings())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Jacklyn API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "database": engine.dialect.name}

    @api.get("/me", response_model=UserOut, tags=["meta"])
    def me(user: CurrentUser) -> UserOut:
        return UserOut.model_validate(user)

    api.include_router(portfolio.router)
    api.include_router(accounts.router)
    api.include_router(imports.router)
    app.include_router(api)
    return app


app = create_app()
