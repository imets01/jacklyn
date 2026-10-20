import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app import __version__
from app.api import api_router
from app.config import get_settings
from app.db import SessionLocal, engine
from app.db.migrate import upgrade_to_head
from app.security.throttle import LoginThrottle
from app.seed import seed
from app.services.auth import SetupGuard, needs_setup, purge_expired_sessions
from app.services.backups import BackupService
from app.services.market_data import MarketDataService
from app.services.sync import SyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO, and IBKR's Flex Web Service takes the token as a query parameter.
logging.getLogger("httpx").setLevel(logging.WARNING)
# yfinance logs every probed symbol that does not exist as an ERROR; listing lookups expect misses and the
# market data service reports real failures itself.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

CSRF_HEADER = "x-jacklyn-request"
CACHEABLE_API = re.compile(r"/api/(assets/\d+/logo|logos/[a-z]+:[A-Z0-9]+)")
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    upgrade_to_head(settings.database_url)
    app.state.login_throttle = LoginThrottle(settings.login_ip_max_failures)
    app.state.setup_guard = SetupGuard()
    with SessionLocal() as session:
        seed(session, settings)
        purge_expired_sessions(session)
        if needs_setup(session):
            app.state.setup_guard.arm()
    app.state.market = MarketDataService(SessionLocal, settings)
    app.state.market.refresh_in_background()
    app.state.sync = SyncService(SessionLocal, on_imported=app.state.market.holdings_changed)
    if settings.live_market_data:  # offline mode (and tests) never reach out to IBKR on their own
        app.state.sync.start_scheduler()
    app.state.backups = BackupService(engine, settings.data_dir)
    if settings.auto_backups:
        app.state.backups.start_scheduler()
    yield
    app.state.sync.stop()
    app.state.backups.stop()


def _same_origin(request: Request) -> bool:
    """Browsers send Origin on cross-site writes; it must name this very host."""
    origin = request.headers.get("origin")
    if origin is None:
        return True
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return urlsplit(origin).netloc == host


def create_app() -> FastAPI:
    app = FastAPI(title="Jacklyn API", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def protect(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        is_api = request.url.path.startswith("/api/")
        # CSRF: state-changing API calls must come from our own UI. A custom header can't be set by a
        # cross-site form or image, and cross-origin fetches with it would need a CORS preflight we never grant.
        if (
            is_api
            and request.method in UNSAFE_METHODS
            and (request.headers.get(CSRF_HEADER) != "1" or not _same_origin(request))
        ):
            return JSONResponse({"detail": "Request blocked (cross-site request protection)."}, status_code=403)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        # Financial data never sits in a cache; versioned logo images are the one exception.
        if is_api and not (response.status_code == 200 and CACHEABLE_API.fullmatch(request.url.path)):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(api_router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
