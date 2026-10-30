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


def calibrate(image: np.ndarray, options: CalibrationOptions, kind: Literal["upload", "camera"], acquired_at: datetime) -> CalibrationResult:
    image = correct_lens(image, options.lens)
    calibration = find_calibration(image, options.settings)
    return CalibrationResult(source=source_info(image, kind, acquired_at, options.lens is not None),
        table_status="detected" if calibration else "searching", calibration=calibration,
        geometry=table_geometry(calibration, options.settings.table_ratio, options.lens is not None) if calibration else None)


def analyze(image: np.ndarray, options: AnalysisOptions, kind: Literal["upload", "camera"], acquired_at: datetime) -> AnalysisResult:
    start = perf_counter()
    image = correct_lens(image, options.lens)
    calibration = options.calibration if options.calibration is not None else find_calibration(image, options.settings)
    detection = None
    if calibration is not None:
        result = detect(image, DetectionRequest(calibration=calibration, settings=options.settings))
        # Explicit public fields prevent engine display colors becoming API dependencies.
        balls = [Ball.model_validate({key: ball[key] for key in Ball.model_fields}) for ball in result["balls"]]
        counts = Counts(total=len(balls), **{
            category: sum(ball.kind == category for ball in balls)
            for category in ("cue", "eight", "solid", "striped", "unknown")
        })
        detection = Detection(balls=balls, counts=counts,
            geometry=table_geometry(calibration, options.settings.table_ratio, options.lens is not None),
            cloth_hue=result["cloth_hue"], processing_ms=result["processing_ms"], warnings=result["warnings"])
    return AnalysisResult(frame_id=str(uuid4()), client_frame_id=options.client_frame_id,
        table_status="detected" if detection is not None else "searching",
        source=source_info(image, kind, acquired_at, options.lens is not None), calibration=calibration,
        settings=options.settings, detection=detection, analysis_ms=round((perf_counter() - start) * 1000, 2))
