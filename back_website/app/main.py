"""Website backend composition; run from back_website/ with uvicorn app.main:app."""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from .api.routes import router
from .api.states import router as states_router
from .schemas import ErrorResponse, Health
from .table_state.config import WatchConfig
from .table_state.database import Database
from .table_state.pi_client import PiClient
from .table_state.watcher import TableWatcher

VERSION = "1.0.0"


def create_app(database_url: str | None = None, watch_config: WatchConfig | None = None,
               pi_client: PiClient | None = None) -> FastAPI:
    """database_url/watch_config default to DATABASE_URL and the TABLE_WATCH_* / PI_URL variables."""
    db = Database(database_url)
    watch_config = watch_config or WatchConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.create_schema()
        watcher = app.state.watcher
        if watcher is not None:
            watcher.start()
        try:
            yield
        finally:
            if watcher is not None:
                watcher.stop()
            db.dispose()

    application = FastAPI(
        lifespan=lifespan,
        title="IoT-eBilard Website API",
        version=VERSION,
        description=(
            "Backend for the web application: configuration (default detector settings, ball categories) "
            "and shot planning on normalized ball layouts (**POST /api/v1/shots**, /shots/predict, /shots/simulate). "
            "Ball recognition runs on the Raspberry Pi service (back_raspberry/, POST /api/v1/camera/detect). "
            "A background watcher polls the Pi, waits until the balls stop moving after a change and stores "
            "the settled layout in the table state database (**/api/v1/states**, live frame at /api/v1/table/live). "
            "Responses are numerical JSON only; the frontend owns rendering."
        ),
        responses={422: {"model": ErrorResponse, "description": "Invalid layout or options"},
                   503: {"model": ErrorResponse, "description": "Processing busy; retry sequentially"}},
    )
    application.state.processing_slot = threading.BoundedSemaphore(1)
    application.state.db = db
    application.state.watcher = (TableWatcher(watch_config, db.session_factory, pi=pi_client)
                                 if watch_config.enabled else None)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request, error: RequestValidationError):
        # Never echo raw input (or non-finite values) into a validation response.
        detail = "; ".join(f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}" for issue in error.errors())
        return JSONResponse(status_code=422, content={"detail": detail})

    @application.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    @application.get("/health", response_model=Health, tags=["Health"])
    def health():
        """Process health."""
        return {"status": "ok", "service": "website", "version": VERSION}

    application.include_router(router)
    application.include_router(states_router)
    return application


app = create_app()
