"""Raspberry Pi service composition; run from back_raspberry/ with uvicorn app.main:app."""

import threading

import cv2
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from .api.routes import router
from .config import ServerConfig
from .schemas import ErrorResponse, Health
from .services.camera import Camera


def create_app(config: ServerConfig | None = None) -> FastAPI:
    config = config or ServerConfig.from_env()
    cv2.setNumThreads(config.opencv_threads)
    application = FastAPI(
        title="IoT-eBilard Raspberry Pi Camera API",
        version="1.0.0",
        description=(
            "Runs on the Raspberry Pi next to the table: captures a frame from the server camera "
            "and recognizes pool balls with CPU-only OpenCV (**POST /api/v1/camera/detect**). "
            "Responses are numerical JSON only: categories, counts, normalized centers/radii, "
            "and source-pixel to normalized-table homographies and their inverses. "
            "Calibration, lens correction and settings are per request, as typed JSON bodies. "
            "Shot planning and configuration are served by the website backend."
        ),
        responses={413: {"model": ErrorResponse, "description": "Captured frame exceeds pixel limits"},
                   422: {"model": ErrorResponse, "description": "Invalid settings or calibration"},
                   503: {"model": ErrorResponse, "description": "Processing busy or camera unavailable; retry sequentially"}},
    )
    application.state.processing_slot = threading.BoundedSemaphore(1)
    application.state.camera = Camera(config)

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
        """Process health; camera availability is checked separately during capture."""
        return {"status": "ok", "engine": "OpenCV", "opencv_version": cv2.__version__, "version": "1.0.0"}

    application.include_router(router)
    return application


app = create_app()
