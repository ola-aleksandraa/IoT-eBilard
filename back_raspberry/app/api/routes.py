"""Numerical HTTP interface of the Raspberry Pi service. All application responses are JSON.

The Pi owns the camera: it captures a frame and analyses it locally. Configuration
and shot planning live in the website backend (back_website/).
"""

from fastapi import APIRouter, Body, Depends, Request

from ..schemas import AnalysisOptions, AnalysisResult, CalibrationOptions, CalibrationResult, CameraStatus
from ..services.analysis import analyze, calibrate
from .dependencies import processing_slot

router = APIRouter(prefix="/api/v1")
guarded = [Depends(processing_slot)]
OPTIONS_EXAMPLES = {
    "automatic": {"summary": "Automatic table calibration", "value": {}},
    "tuned": {"summary": "Tune geometry and correlate a client frame", "value": {
        "settings": {"table_ratio": 2, "ball_radius_ratio": 0.026}, "client_frame_id": "frame-1",
    }},
}


@router.get("/camera", response_model=CameraStatus, tags=["Camera"])
def camera_status(request: Request):
    """Inspect server camera configuration without activating it."""
    return request.app.state.camera.status()


@router.post("/camera/calibrate", response_model=CalibrationResult, tags=["Camera"], dependencies=guarded)
def camera_calibrate(request: Request, options: CalibrationOptions | None = Body(default=None,
    openapi_examples={"automatic": {"summary": "Automatic calibration", "value": {}}})):
    """Capture internally and return only table calibration/geometry JSON."""
    image, acquired_at = request.app.state.camera.capture()
    return calibrate(image, options or CalibrationOptions(), "camera", acquired_at)


@router.post("/camera/detect", response_model=AnalysisResult, tags=["Camera"], dependencies=guarded)
def camera_detect(request: Request, options: AnalysisOptions | None = Body(default=None, openapi_examples=OPTIONS_EXAMPLES)):
    """Capture internally and return numerical recognition JSON. Poll sequentially.

    CAMERA_SOURCE selects the server device/stream. Every call opens, reads and
    releases it. No raw frame, rendered preview or base64 payload is returned.
    """
    image, acquired_at = request.app.state.camera.capture()
    return analyze(image, options or AnalysisOptions(), "camera", acquired_at)
