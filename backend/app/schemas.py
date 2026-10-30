"""Versioned numerical contracts. Rendering and test fixtures are client concerns."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ShotBall(BaseModel):
    """Only the numerical layout is needed; detection evidence is ignored."""
    id: int
    kind: BallKind
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    radius: float = Field(gt=0, le=0.2)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class ShotLayout(StrictModel):
    balls: list[ShotBall] = Field(max_length=24)
    table_ratio: float = Field(default=2, ge=1, le=3)

    @field_validator("balls")
    @classmethod
    def unique_ids(cls, balls):
        if len({ball.id for ball in balls}) != len(balls):
            raise ValueError("Ball IDs must be unique within a layout.")
        return balls


class ShotsRequest(ShotLayout):
    top_n: int = Field(default=5, ge=1, le=20)
    include_bank: bool = True
    include_blocked: bool = False


class PredictRequest(ShotLayout):
    aim_x: float = Field(ge=0, le=1)
    aim_y: float = Field(ge=0, le=1)


class SimulateRequest(PredictRequest):
    power: float = Field(default=0.6, ge=0, le=1)


LayoutStatus = Literal["ok", "no_cue_ball", "multiple_cue_balls", "no_targets"]
AimStatus = Literal["ok", "no_cue_ball", "multiple_cue_balls", "no_targets", "invalid_aim"]
PathPoint = tuple[float, float]


class ScoreComponents(StrictModel):
    pocket_probability: float
    position_value: float
    difficulty_penalty: float


class Shot(StrictModel):
    target_ball: int = Field(description="Legacy zero-based index in the submitted layout; prefer target_ball_id.")
    target_ball_id: int
    pocket: int = Field(ge=0, le=5)
    shot_type: Literal["direct", "bank"]
    score: float
    score_components: ScoreComponents
    cut_angle: float
    path_length: float = Field(description="Legacy engine distance at table width 1000; paths use normalized table coordinates.")
    is_blocked: bool
    blocked_reason: str
    velocity_remaining: float
    cue_path: list[PathPoint]
    target_path: list[PathPoint]
    cue_deflect_path: list[PathPoint]
    ghost_pos: PathPoint | None
    bank_cushion: str | None
    bank_point: PathPoint | None


class ShotsResult(StrictModel):
    status: LayoutStatus
    cue_ball_id: int | None
    shots: list[Shot]
    blocked: list[Shot]


class PredictionResult(StrictModel):
    status: AimStatus
    cue_ball_id: int | None
    first_ball_id: int | None
    ghost_pos: PathPoint | None = None
    cut_angle: float | None = None
    pocket: int | None = None
    makeable: bool = False
    blocked_reason: str | None = None
    velocity_remaining: float = 0
    score: float = 0
    cue_path: list[PathPoint] = Field(default_factory=list)
    target_path: list[PathPoint] = Field(default_factory=list)
    cue_deflect_path: list[PathPoint] = Field(default_factory=list)
    bank_point: PathPoint | None = None


class MotionEvent(StrictModel):
    t: float
    type: Literal["contact", "cushion", "pot"]
    ball: int
    with_: int | None = Field(default=None, alias="with")
    pocket: int | None = None
    x: float | None = None
    y: float | None = None
    cut_angle: float | None = None


class MotionBall(StrictModel):
    id: int
    path: list[PathPoint]
    potted_t: float | None


class SimulationResult(StrictModel):
    status: AimStatus
    cue_ball_id: int | None
    first_ball_id: int | None
    ghost_pos: PathPoint | None = None
    cut_angle: float | None = None
    power: float = 0
    duration: float = 0
    dt: float = 0.025
    balls: list[MotionBall] = Field(default_factory=list)
    events: list[MotionEvent] = Field(default_factory=list)
    potted: list[int] = Field(default_factory=list)
