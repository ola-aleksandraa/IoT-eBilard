"""Stateless numerical orchestration shared by uploads and server-camera capture."""

from datetime import datetime
from time import perf_counter
from typing import Literal
from uuid import uuid4

import numpy as np
from pydantic import ValidationError

from ..engine.models import Calibration, DetectionRequest, Settings
from ..engine.vision import detect, suggest_corners
from ..schemas import AnalysisOptions, AnalysisResult, Ball, CalibrationOptions, CalibrationResult, Counts, Detection, Source
from .geometry import table_geometry
from .images import correct_lens
from .auto_lens import estimate_table_lens


def find_calibration(image: np.ndarray, settings: Settings) -> Calibration | None:
    height, width = image.shape[:2]
    corners = suggest_corners(image, settings)
    if corners is None:
        return None
    try:
        return Calibration(corners=corners, image_width=width, image_height=height)
    except ValidationError:
        return None


def source_info(image: np.ndarray, kind: Literal["upload", "camera"], acquired_at: datetime, corrected: bool) -> Source:
    height, width = image.shape[:2]
    return Source(kind=kind, width=width, height=height, acquired_at=acquired_at, lens_corrected=corrected)


def automatic_calibration(image, settings, explicit_lens):
    """Lens fitting is a calibration step, never a per-frame adjustment of a lock."""
    image = correct_lens(image, explicit_lens)
    calibration = find_calibration(image, settings)
    if explicit_lens is None:
        lens = estimate_table_lens(image, settings)
        if lens is not None:
            corrected = correct_lens(image, lens)
            refined = find_calibration(corrected, settings)
            # A straightened boundary must still pass normal table detection.
            if refined is not None:
                return corrected, refined.model_copy(update={"lens": lens,
                    "native_corners": calibration.corners if calibration is not None else None})
    return image, calibration


def calibrate(image: np.ndarray, options: CalibrationOptions, kind: Literal["upload", "camera"], acquired_at: datetime) -> CalibrationResult:
    image, calibration = automatic_calibration(image, options.settings, options.lens)
    corrected = options.lens is not None or (calibration is not None and calibration.lens is not None)
    return CalibrationResult(source=source_info(image, kind, acquired_at, corrected),
        table_status="detected" if calibration else "searching", calibration=calibration,
        geometry=table_geometry(calibration, options.settings.table_ratio, corrected) if calibration else None)


def analyze(image: np.ndarray, options: AnalysisOptions, kind: Literal["upload", "camera"], acquired_at: datetime) -> AnalysisResult:
    start = perf_counter()
    original = image
    if options.calibration is None:
        image, calibration = automatic_calibration(image, options.settings, options.lens)
    else:
        calibration = options.calibration
        # An automatic lens acts on geometry inside the engine. Native source
        # silhouettes/colors are recognized without resampling the ball bodies.
        image = correct_lens(image, options.lens)
    corrected = options.lens is not None or (calibration is not None and calibration.lens is not None)
    detection = None
    if calibration is not None:
        result = detect(original if calibration.lens is not None else image,
                        DetectionRequest(calibration=calibration, settings=options.settings))
        # Explicit public fields prevent engine display colors becoming API dependencies.
        balls = [Ball.model_validate({key: ball[key] for key in Ball.model_fields}) for ball in result["balls"]]
        counts = Counts(total=len(balls), **{
            category: sum(ball.kind == category for ball in balls)
            for category in ("cue", "eight", "solid", "striped", "unknown")
        })
        detection = Detection(balls=balls, counts=counts,
            geometry=table_geometry(calibration, options.settings.table_ratio, corrected),
            cloth_hue=result["cloth_hue"], processing_ms=result["processing_ms"], warnings=result["warnings"])
    return AnalysisResult(frame_id=str(uuid4()), client_frame_id=options.client_frame_id,
        table_status="detected" if detection is not None else "searching",
        source=source_info(image, kind, acquired_at, corrected), calibration=calibration,
        settings=options.settings, detection=detection, analysis_ms=round((perf_counter() - start) * 1000, 2))
