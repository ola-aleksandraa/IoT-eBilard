"""Numerical HTTP interface. All application responses are JSON."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile

from ..engine.models import Settings
from ..schemas import AnalysisOptions, AnalysisResult, CalibrationOptions, CalibrationResult, CameraStatus, Category, PredictRequest, ShotsRequest, SimulateRequest
from ..services.analysis import analyze, calibrate
from ..services.images import parse_json, read_image
from ..trajectory import plan_shots, predict_shot, simulate_motion
from .dependencies import processing_slot

router = APIRouter(prefix="/api/v1")
guarded = [Depends(processing_slot)]
CONFIG_HELP = ('AnalysisOptions JSON: {"calibration":null,"settings":{"table_ratio":2,'
               '"ball_radius_ratio":0.026},"client_frame_id":"frame-1"}. '
               'Omit calibration for automatic corners. Optional lens correction is internal. '
               'See AnalysisOptions under Schemas. Responses contain numerical JSON only.')
OPTIONS_EXAMPLES = {
    "automatic": {"summary": "Automatic table calibration", "value": {}},
    "tuned": {"summary": "Tune geometry and correlate a client frame", "value": {
        "settings": {"table_ratio": 2, "ball_radius_ratio": 0.026}, "client_frame_id": "frame-1",
    }},
}


@router.get("/settings", response_model=Settings, tags=["Configuration"])
def settings():
    """Default per-request detector settings."""
    return Settings()


@router.get("/categories", response_model=list[Category], tags=["Configuration"])
def categories():
    """Recognition vocabulary. The client selects colors, patterns and rendering."""
    return [Category(kind=kind, description=description) for kind, description in [
        ("cue", "Cue ball; at most one per frame."), ("eight", "Eight ball; at most one per frame."),
        ("solid", "Solid/full pattern."), ("striped", "Striped/half pattern."),
        ("unknown", "Located candidate with insufficient category evidence."),
    ]]


@router.post("/images/calibrate", response_model=CalibrationResult, tags=["Images"], dependencies=guarded)
def calibrate_image(file: UploadFile = File(...), config: str = Form("{}", description="CalibrationOptions JSON: optional lens and settings.")):
    """Return normalized inner-cushion corners and homographies, without pixels.

    Reuse calibration with matching camera position, crop, dimensions and lens
    correction. Source coordinates refer to EXIF-oriented/corrected pixels.
    """
    options = parse_json(CalibrationOptions, config)
    image = read_image(file)
    return calibrate(image, options, "upload", datetime.now(timezone.utc))


@router.post("/images/detect", response_model=AnalysisResult, tags=["Images"], dependencies=guarded)
def detect_image(file: UploadFile = File(...), config: str = Form("{}", description=CONFIG_HELP)):
    """Image in → ball categories, counts, normalized positions and geometry out.

    The client renders x*W, y*H and radius*H on a W/H=table_ratio rectangle.
    IDs are frame-local and confidence is heuristic. A lost table returns
    searching and detection=null, never stale positions. No image is returned.
    """
    options = parse_json(AnalysisOptions, config)
    image = read_image(file)
    return analyze(image, options, "upload", datetime.now(timezone.utc))


@router.get("/camera", response_model=CameraStatus, tags=["Camera"])
def camera_status(request: Request):
    """Inspect server camera configuration without activating it."""
    return request.app.state.camera.status()


@router.post("/camera/calibrate", response_model=CalibrationResult, tags=["Camera"], dependencies=guarded)
def camera_calibrate(request: Request, options: Optional[CalibrationOptions] = Body(default=None,
    openapi_examples={"automatic": {"summary": "Automatic calibration", "value": {}}})):
    """Capture internally and return only table calibration/geometry JSON."""
    image, acquired_at = request.app.state.camera.capture()
    return calibrate(image, options or CalibrationOptions(), "camera", acquired_at)


@router.post("/camera/detect", response_model=AnalysisResult, tags=["Camera"], dependencies=guarded)
def camera_detect(request: Request, options: Optional[AnalysisOptions] = Body(default=None, openapi_examples=OPTIONS_EXAMPLES)):
    """Capture internally and return numerical recognition JSON. Poll sequentially.

    CAMERA_SOURCE selects the server device/stream. Every call opens, reads and
    releases it. No raw frame, rendered preview or base64 payload is returned.
    """
    image, acquired_at = request.app.state.camera.capture()
    return analyze(image, options or AnalysisOptions(), "camera", acquired_at)


@router.post("/shots", tags=["Shots"], dependencies=guarded)
def shots(options: ShotsRequest) -> Dict:
    """Rank direct and bank shots using normalized ball positions; return numerical paths."""
    return plan_shots(options.balls, options.table_ratio, options.top_n,
                      options.include_bank, options.include_blocked)


@router.post("/shots/predict", tags=["Shots"], dependencies=guarded)
def predict(options: PredictRequest) -> Dict:
    """Predict the first contact and pocket paths for a cue aim."""
    return predict_shot(options.balls, options.table_ratio, (options.aim_x, options.aim_y))


@router.post("/shots/simulate", tags=["Shots"], dependencies=guarded)
def simulate(options: SimulateRequest) -> Dict:
    """Roll out a cue aim with collisions, cushions and pots as time-sampled coordinates."""
    return simulate_motion(options.balls, options.table_ratio,
                           (options.aim_x, options.aim_y), options.power)
