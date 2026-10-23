"""Versioned numerical contracts. Rendering and test fixtures are client concerns."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .engine.models import Calibration, LensCalibration, LiveRequest, Settings, StrictModel

BallKind = Literal["cue", "eight", "solid", "striped", "unknown"]
Matrix3x3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


class AnalysisOptions(LiveRequest):
    lens: LensCalibration | None = Field(default=None, description=(
        "Optional internal lens correction. Source coordinates then refer to undistorted, EXIF-oriented pixels."
    ))
    client_frame_id: str | None = Field(default=None, max_length=128, description="Optional caller frame token, echoed unchanged.")


class Source(StrictModel):
    kind: Literal["upload", "camera"]
    width: int = Field(ge=100)
    height: int = Field(ge=100)
    acquired_at: datetime = Field(description="Server acquisition time; uploads use time after decode, not camera exposure time.")
    lens_corrected: bool


class Counts(StrictModel):
    total: int = Field(ge=0)
    cue: int = Field(ge=0, le=1)
    eight: int = Field(ge=0, le=1)
    solid: int = Field(ge=0)
    striped: int = Field(ge=0)
    unknown: int = Field(ge=0)


class Ball(StrictModel):
    id: int = Field(ge=1, description="Frame-local label, not printed number or persistent identity.")
    kind: BallKind
    x: float = Field(ge=0, le=1, description="Center / table width, left to right.")
    y: float = Field(ge=0, le=1, description="Center / table height, top to bottom.")
    radius: float = Field(gt=0, description="Radius / table height; render a circle, not an ellipse.")
    source_x: float = Field(ge=0, le=1, description="Center / oriented or corrected source width.")
    source_y: float = Field(ge=0, le=1, description="Center / oriented or corrected source height.")
    confidence: float = Field(ge=0, le=1, description="Heuristic rule score, not calibrated probability.")
    reason: str
    white_fraction: float = Field(ge=0, le=1)
    method: str


class Geometry(StrictModel):
    table_ratio: float = Field(ge=1, le=3, description="Physical cloth width / height; preserve when rendering.")
    source_to_table: Matrix3x3 = Field(description="Source PIXELS → normalized table [0,1]. Divide by homogeneous third coordinate.")
    table_to_source: Matrix3x3 = Field(description="Inverse: normalized table [0,1] → source PIXELS.")
    origin: Literal["top_left"] = "top_left"
    x_direction: Literal["right"] = "right"
    y_direction: Literal["down"] = "down"
    center_unit: Literal["normalized_table"] = "normalized_table"
    radius_unit: Literal["table_height"] = "table_height"
    source_space: Literal["oriented_pixels", "undistorted_oriented_pixels"]


class Detection(StrictModel):
    balls: list[Ball]
    counts: Counts
    geometry: Geometry
    cloth_hue: int | None = Field(ge=0, le=179)
    processing_ms: float = Field(ge=0, description="Engine localization/classification time; excludes acquisition/decode/calibration.")
    warnings: list[str]


class AnalysisResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    frame_id: str = Field(description="Unique server analysis identifier.")
    client_frame_id: str | None
    table_status: Literal["detected", "searching"]
    source: Source
    calibration: Calibration | None
    settings: Settings
    detection: Detection | None
    analysis_ms: float = Field(ge=0, description="Includes lens correction/calibration; excludes acquisition/decode/network.")


class CalibrationResult(StrictModel):
    source: Source
    table_status: Literal["detected", "searching"]
    calibration: Calibration | None
    geometry: Geometry | None


class CalibrationOptions(StrictModel):
    lens: LensCalibration | None = None
    settings: Settings = Field(default_factory=Settings)


class Category(StrictModel):
    kind: BallKind
    description: str


class CameraStatus(StrictModel):
    source_kind: Literal["device", "stream", "file"]
    device_index: int | None
    capture_mode: Literal["per_request"] = "per_request"
    requested_width: int
    requested_height: int
    warmup_frames: int
    note: str


class Health(StrictModel):
    status: Literal["ok"]
    engine: Literal["OpenCV"]
    opencv_version: str
    version: str


class ErrorResponse(StrictModel):
    detail: str
