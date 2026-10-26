from typing import List, Optional
from typing_extensions import Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field, root_validator


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"
        allow_inf_nan = False


class Point(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Settings(StrictModel):
    table_ratio: float = Field(default=2, ge=1, le=3)
    ball_radius_ratio: float = Field(default=0.026, ge=0.012, le=0.06)
    cloth_hue: Optional[int] = Field(default=None, ge=0, le=179)
    hue_tolerance: int = Field(default=16, ge=3, le=40)
    saturation_min: int = Field(default=55, ge=15, le=180)
    split_touching: bool = True


class Calibration(StrictModel):
    corners: List[Point] = Field(min_items=4, max_items=4)
    image_width: int = Field(gt=0, le=10000)
    image_height: int = Field(gt=0, le=10000)

    @root_validator(skip_on_failure=True)
    def valid_quad(cls, values):
        points_list = values.get("corners")
        if points_list is None:
            return values
        points = np.float32([[p.x, p.y] for p in points_list])
        # Clockwise image coordinates have positive area; the first edge
        # maps to canvas width and should follow the physical long side.
        if not cv2.isContourConvex(points) or cv2.contourArea(points, oriented=True) < 0.025:
            raise ValueError("Corners must form a clockwise, convex table; start along its long edge.")
        return values


class DetectionRequest(StrictModel):
    calibration: Calibration
    settings: Settings = Field(default_factory=Settings)


class LiveRequest(StrictModel):
    calibration: Optional[Calibration] = None
    settings: Settings = Field(default_factory=Settings)


class LensCalibration(StrictModel):
    image_width: int = Field(gt=0, le=10000)
    image_height: int = Field(gt=0, le=10000)
    camera_matrix: List[List[float]]
    distortion: List[float] = Field(min_items=4, max_items=14)

    @root_validator(skip_on_failure=True)
    def valid_matrix(cls, values):
        camera_matrix = values.get("camera_matrix")
        distortion = values.get("distortion")
        if camera_matrix is None or distortion is None:
            return values
        k = np.asarray(camera_matrix)
        if k.shape != (3, 3) or not np.isfinite(k).all():
            raise ValueError("camera_matrix must be a finite 3 × 3 matrix.")
        if k[0, 0] <= 0 or k[1, 1] <= 0 or not np.allclose(k[2], [0, 0, 1]):
            raise ValueError("Invalid camera intrinsics.")
        if len(distortion) not in (4, 5, 8, 12, 14):
            raise ValueError("OpenCV distortion requires 4, 5, 8, 12, or 14 coefficients.")
        return values


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
