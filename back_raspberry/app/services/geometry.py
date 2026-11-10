"""Mapping between camera pixels and a normalized rectangular cloth plane."""

import cv2
import numpy as np

from ..engine.models import Calibration
from ..schemas import Geometry


def table_geometry(calibration: Calibration, table_ratio: float, lens_corrected: bool) -> Geometry:
    source = np.float32([[p.x * (calibration.image_width - 1), p.y * (calibration.image_height - 1)]
                         for p in calibration.corners])
    target = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
    forward = cv2.getPerspectiveTransform(source, target)
    inverse = np.linalg.inv(forward)
    return Geometry(table_ratio=table_ratio, source_to_table=forward.tolist(), table_to_source=inverse.tolist(),
                    source_space="undistorted_oriented_pixels" if lens_corrected else "oriented_pixels")
