"""Website backend composition; run from back_website/ with uvicorn app.main:app."""

import threading

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from .api.routes import router
from .schemas import ErrorResponse, Health

VERSION = "1.0.0"


def create_app() -> FastAPI:
    application = FastAPI(
        title="IoT-eBilard Website API",
        version=VERSION,
        description=(
            "Backend for the web application: configuration (default detector settings, ball categories) "
            "and shot planning on normalized ball layouts (**POST /api/v1/shots**, /shots/predict, /shots/simulate). "
            "Ball recognition runs on the Raspberry Pi service (back_raspberry/, POST /api/v1/camera/detect). "
            "Responses are numerical JSON only; the frontend owns rendering."
        ),
        responses={422: {"model": ErrorResponse, "description": "Invalid layout or options"},
                   503: {"model": ErrorResponse, "description": "Processing busy; retry sequentially"}},
    )
    application.state.processing_slot = threading.BoundedSemaphore(1)

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
    return application


app = create_app()
