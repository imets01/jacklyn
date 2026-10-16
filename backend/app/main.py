import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.config import get_settings
from app.db import SessionLocal
from app.db.migrate import upgrade_to_head
from app.seed import seed
from app.services.market_data import MarketDataService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    upgrade_to_head(settings.database_url)
    with SessionLocal() as session:
        seed(session, settings)
    app.state.market = MarketDataService(SessionLocal, settings)
    app.state.market.refresh_in_background()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Jacklyn API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
