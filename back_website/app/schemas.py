"""Versioned numerical contracts of the website backend: configuration and shot planning.

Recognition contracts (AnalysisResult, Calibration, ...) live in back_raspberry/app/schemas.py.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BallKind = Literal["cue", "eight", "solid", "striped", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Settings(StrictModel):
    """Default per-request detector settings sent to the Raspberry Pi camera routes.

    Keep in sync with Settings in back_raspberry/app/engine/models.py, which validates them.
    """
    table_ratio: float = Field(default=2, ge=1, le=3)
    ball_radius_ratio: float = Field(default=0.026, ge=0.012, le=0.06)
    cloth_hue: int | None = Field(default=None, ge=0, le=179)
    hue_tolerance: int = Field(default=16, ge=3, le=40)
    saturation_min: int = Field(default=55, ge=15, le=180)
    split_touching: bool = True


class Category(StrictModel):
    kind: BallKind
    description: str


class Health(StrictModel):
    status: Literal["ok"]
    service: Literal["website"]
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
