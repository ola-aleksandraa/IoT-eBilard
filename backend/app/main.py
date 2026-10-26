"""Application composition; run from backend/ with uvicorn app.main:app."""

import threading
from typing import Optional

import cv2
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from .api.routes import router
from .config import ServerConfig
from .schemas import ErrorResponse, Health
from .services.camera import Camera


def create_app(config: Optional[ServerConfig] = None) -> FastAPI:
    config = config or ServerConfig.from_env()
    cv2.setNumThreads(config.opencv_threads)
    application = FastAPI(
        title="IoT-eBilard Ball Recognition API",
        version="1.0.0",
        description=(
            "Standalone, CPU-only pool-ball recognition using the original PoC mathematics. "
            "Upload a frame with **POST /api/v1/images/detect**, or capture internally with /api/v1/camera/detect. "
            "Application endpoints return numerical JSON only: categories, counts, normalized centers/radii, "
            "and source-pixel to normalized-table homographies and their inverses. The frontend owns rendering. "
            "Calibration, lens correction and settings are per request. "
            "Uploads use multipart file + JSON config string; camera requests use typed JSON bodies."
        ),
        responses={413: {"model": ErrorResponse, "description": "Image exceeds byte or pixel limits"},
                   415: {"model": ErrorResponse, "description": "Unsupported image format"},
                   422: {"model": ErrorResponse, "description": "Invalid image, settings or calibration"},
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
