from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class Calibration(StrictModel):
    corners: list[Point] = Field(min_length=4, max_length=4)
    image_width: int = Field(gt=0, le=10000)
    image_height: int = Field(gt=0, le=10000)
    lens: LensCalibration | None = Field(default=None, description=(
        "Automatic table-derived lens correction. Corners refer to corrected pixels; "
        "reuse the whole calibration with original frames from the same view."
    ))
    native_corners: list[Point] | None = Field(default=None, min_length=4, max_length=4, description=(
        "Original coarse rail intersections retained with an automatic lens fit for native-pixel "
        "ball proposal sizing. Table coordinates always use the corrected corners."
    ))

    @model_validator(mode="after")
    def valid_quad(self):
        if self.lens and (self.lens.image_width, self.lens.image_height) != (self.image_width, self.image_height):
            raise ValueError("Embedded lens resolution must match the table calibration.")
        if self.native_corners is not None:
            native = np.float32([[p.x, p.y] for p in self.native_corners])
            if self.lens is None or not cv2.isContourConvex(native) or cv2.contourArea(native, oriented=True) < .025:
                raise ValueError("Native corners require a lens and a clockwise convex quadrilateral.")
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
