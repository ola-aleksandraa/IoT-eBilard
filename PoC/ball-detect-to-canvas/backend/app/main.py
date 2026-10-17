import io
import os
import threading
import warnings

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from .demo import demo_response
from .models import Calibration, DetectionRequest, LensCalibration, LiveRequest, ShotsRequest
from .trajectory import plan_shots
from .vision import detect, image_url, suggest_corners

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
cv2.setNumThreads(max(1, min(4, os.cpu_count() or 1)))
# Bound memory / CPU for a local Pi deployment. Excess concurrent requests fail fast.
processing_slot = threading.BoundedSemaphore(1)
app = FastAPI(title="Ball / Detect API", version="0.1.0", description="Deterministic settled-frame pool-ball detection. No neural models.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","), allow_methods=["GET", "POST"], allow_headers=["*"])


def read_image(file: UploadFile, *, canonical=False) -> np.ndarray:
    # Canonical PNGs can be larger than the compressed original after EXIF/lens
    # correction. Keep the same pixel ceiling but allow their lossless payload.
    byte_limit = 64 * 1024 * 1024 if canonical else MAX_UPLOAD_BYTES
    data = file.file.read(byte_limit + 1)
    if len(data) > byte_limit:
        raise HTTPException(413, f"Image exceeds the {byte_limit // 1024 // 1024} MB upload limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise HTTPException(415, "Use a JPEG, PNG, or WebP image.")
                if source.width * source.height > MAX_PIXELS or max(source.size) > 10000:
                    raise HTTPException(413, "Images must be at most 16 megapixels and 10,000 pixels per side.")
                if min(source.size) < 100:
                    raise HTTPException(422, "Image is too small; each side must be at least 100 pixels.")
                image = ImageOps.exif_transpose(source).convert("RGB")
                return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(422, "The uploaded file is not a readable image.") from None
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, "Image exceeds the safe pixel limit.") from None


def parse_json(model, value):
    try:
        return model.model_validate_json(value)
    except ValidationError as exc:
        errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise HTTPException(422, errors) from None


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "OpenCV", "opencv_version": cv2.__version__}


@app.get("/api/demo")
def demo():
    return demo_response()


@app.post("/api/prepare")
def prepare(file: UploadFile = File(...), lens: str | None = Form(None)):
    """Normalize EXIF orientation, optionally undistort, then suggest corners.

    All later calibration/detection uses the returned canonical PNG. Intrinsics
    refer to the EXIF-oriented input at exactly the specified resolution.
    """
    image = read_image(file)
    if lens:
        calibration = parse_json(LensCalibration, lens)
        height, width = image.shape[:2]
        if (width, height) != (calibration.image_width, calibration.image_height):
            raise HTTPException(422, "Lens calibration resolution must match the oriented image.")
        image = cv2.undistort(image, np.float64(calibration.camera_matrix), np.float64(calibration.distortion))
    height, width = image.shape[:2]
    return {"image": image_url(image, png=True), "width": width, "height": height,
            "suggested_corners": suggest_corners(image), "lens_corrected": bool(lens)}


@app.post("/api/detect")
def detect_balls(file: UploadFile = File(...), config: str = Form(...)):
    request = parse_json(DetectionRequest, config)
    if not processing_slot.acquire(blocking=False):
        raise HTTPException(503, "Another frame is processing. Try again in a moment.")
    try:
        image = read_image(file, canonical=True)
        return detect(image, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        processing_slot.release()


@app.post("/api/live")
def live_frame(file: UploadFile = File(...), config: str = Form("{}")):
    """Find the table on every frame, then map balls. No image/identity history.

    A supplied calibration is an explicit manual override. Otherwise loss of
    the cloth quadrilateral returns searching, never stale mapped positions.
    """
    request = parse_json(LiveRequest, config)
    if not processing_slot.acquire(blocking=False):
        raise HTTPException(503, "Another frame is processing. Try again in a moment.")
    try:
        image = read_image(file, canonical=True)
        height, width = image.shape[:2]
        calibration = request.calibration
        if calibration is None:
            corners = suggest_corners(image)
            if corners is None:
                return {"table_status": "searching", "calibration": None, "detection": None}
            try:
                calibration = Calibration(corners=corners, image_width=width, image_height=height)
            except ValidationError:
                return {"table_status": "searching", "calibration": None, "detection": None}
        detection = detect(image, DetectionRequest(calibration=calibration, settings=request.settings), debug=False)
        return {"table_status": "detected", "calibration": calibration.model_dump(), "detection": detection}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        processing_slot.release()


@app.post("/api/shots")
def shots(request: ShotsRequest):
    """Ghost-ball shot planning for detected balls.

    Input/output use the same 0-1 table coordinates as /api/detect. Each shot has the cue-ball path,
    target-ball path, cue-ball deflection after contact, ghost-ball position, score and block reason.
    """
    return plan_shots(request.balls, request.table_ratio, request.top_n,
                      request.include_bank, request.include_blocked)
