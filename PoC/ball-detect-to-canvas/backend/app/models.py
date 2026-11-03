from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .trajectory.service import POWER_PRESETS_MPS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Settings(StrictModel):
    table_ratio: float = Field(default=2, ge=1, le=3)
    ball_radius_ratio: float = Field(default=0.026, ge=0.012, le=0.06)
    cloth_hue: int | None = Field(default=None, ge=0, le=179)
    hue_tolerance: int = Field(default=16, ge=3, le=40)
    saturation_min: int = Field(default=55, ge=15, le=180)
    split_touching: bool = True


class Calibration(StrictModel):
    corners: list[Point] = Field(min_length=4, max_length=4)
    image_width: int = Field(gt=0, le=10000)
    image_height: int = Field(gt=0, le=10000)

    @model_validator(mode="after")
    def valid_quad(self):
        points = np.float32([[p.x, p.y] for p in self.corners])
        # Clockwise image coordinates have positive area; the first edge
        # maps to canvas width and should follow the physical long side.
        if not cv2.isContourConvex(points) or cv2.contourArea(points, oriented=True) < 0.025:
            raise ValueError("Corners must form a clockwise, convex table; start along its long edge.")
        return self


class DetectionRequest(StrictModel):
    calibration: Calibration
    settings: Settings = Field(default_factory=Settings)


class LiveRequest(StrictModel):
    calibration: Calibration | None = None
    settings: Settings = Field(default_factory=Settings)


class LensCalibration(StrictModel):
    image_width: int = Field(gt=0, le=10000)
    image_height: int = Field(gt=0, le=10000)
    camera_matrix: list[list[float]]
    distortion: list[float] = Field(min_length=4, max_length=14)

    @model_validator(mode="after")
    def valid_matrix(self):
        k = np.asarray(self.camera_matrix)
        if k.shape != (3, 3) or not np.isfinite(k).all():
            raise ValueError("camera_matrix must be a finite 3 × 3 matrix.")
        if k[0, 0] <= 0 or k[1, 1] <= 0 or not np.allclose(k[2], [0, 0, 1]):
            raise ValueError("Invalid camera intrinsics.")
        if len(self.distortion) not in (4, 5, 8, 12, 14):
            raise ValueError("OpenCV distortion requires 4, 5, 8, 12, or 14 coefficients.")
        return self


class Ball(StrictModel):
    id: int
    kind: Literal["cue", "eight", "solid", "striped", "unknown"]
    x: float
    y: float
    radius: float
    source_x: float
    source_y: float
    color: str
    confidence: float
    reason: str
    white_fraction: float
    method: str


class ShotBall(BaseModel):
    """A detected ball as sent by the frontend. Extra detection fields are ignored."""
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    id: int
    kind: Literal["cue", "eight", "solid", "striped", "unknown"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    radius: float = Field(gt=0, le=0.2)


class ShotsRequest(StrictModel):
    balls: list[ShotBall] = Field(max_length=24)
    table_ratio: float = Field(default=2, ge=1, le=3)
    top_n: int = Field(default=5, ge=1, le=20)
    include_bank: bool = True
    include_blocked: bool = False


class PredictRequest(StrictModel):
    """One cue-stick aim: the cue ball travels toward `aim_x/aim_y` on the table plane."""
    balls: list[ShotBall] = Field(max_length=24)
    table_ratio: float = Field(default=2, ge=1, le=3)
    aim_x: float = Field(ge=0, le=1)
    aim_y: float = Field(ge=0, le=1)


class SimulateRequest(StrictModel):
    """One cue-stick aim rolled out with real 2-D physics (motion prediction).

    `power` is the stroke strength: a real-world preset name (soft / medium /
    hard, see POWER_PRESETS_MPS) or a plain 0-1 fraction of the stroke range.
    """
    balls: list[ShotBall] = Field(max_length=24)
    table_ratio: float = Field(default=2, ge=1, le=3)
    aim_x: float = Field(ge=0, le=1)
    aim_y: float = Field(ge=0, le=1)
    power: float | str = 0.6

    @model_validator(mode="after")
    def normalise_power(self):
        value = self.power
        if isinstance(value, str):
            # Numeric strings behave like numbers; anything else must be a preset.
            try:
                value = float(value)
            except ValueError:
                level = value.strip().lower()
                if level not in POWER_PRESETS_MPS:
                    raise ValueError(
                        "power must be 0-1 or one of the presets: "
                        + ", ".join(sorted(POWER_PRESETS_MPS))) from None
                self.power = level
                return self
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("power must be between 0 and 1, or a preset name: "
                             + ", ".join(sorted(POWER_PRESETS_MPS)))
        return self


class ComparePowerRequest(StrictModel):
    """Roll one aim out at several real-world power levels (default: all three)."""
    balls: list[ShotBall] = Field(max_length=24)
    table_ratio: float = Field(default=2, ge=1, le=3)
    aim_x: float = Field(ge=0, le=1)
    aim_y: float = Field(ge=0, le=1)
    levels: list[str] = Field(default_factory=lambda: list(POWER_PRESETS_MPS))

    @model_validator(mode="after")
    def valid_levels(self):
        unknown = [level for level in self.levels if level.strip().lower() not in POWER_PRESETS_MPS]
        if unknown:
            raise ValueError("Unknown power levels: " + ", ".join(unknown)
                             + ". Use: " + ", ".join(sorted(POWER_PRESETS_MPS)))
        if not self.levels:
            raise ValueError("levels must not be empty.")
        return self
