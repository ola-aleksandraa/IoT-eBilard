"""Conservative single-view plumb-line calibration from the four cloth rails.

Perspective preserves lines: bowed rails (including the two pocket rows) provide
evidence for radial correction before homography. A single frame cannot recover
full camera intrinsics. Fix the optical center at the image center and focal
scale at the longest image side, and fit only k1. No camera-specific constants.
"""

import cv2
import numpy as np

from ..engine.calibration import find_table
from ..engine.models import LensCalibration, Settings


def rail_samples(boundary, corners, diagonal):
    """Bin dense contour pixels equally; omit corner and side-pocket mouths."""
    rails = []
    for a, b in zip(corners, np.roll(corners, -1, axis=0)):
        length = np.linalg.norm(b - a)
        direction = (b - a) / length
        normal = np.array([-direction[1], direction[0]])
        along = (boundary - a) @ direction / length
        offset = (boundary - a) @ normal
        bins = []
        for low in np.linspace(.10, .875, 32):
            if .40 < low < .58:
                continue
            points = boundary[(along >= low) & (along < low + .025) & (np.abs(offset) < diagonal * .045)]
            if len(points) >= 3:
                bins.append(np.median(points, axis=0))
        if len(bins) < 19:
            return None
        points = np.array(bins)
        t = (points - a) @ direction / length
        y = (points - a) @ normal
        # Isolated occlusions/pocket lips must not be interpreted as curvature.
        keep = np.ones(len(points), dtype=bool)
        for _ in range(3):
            fit = np.polyfit(t[keep], y[keep], 2)
            residual = np.abs(y - np.polyval(fit, t))
            keep = residual < max(1.25, 3 * float(np.median(residual)))
            if np.count_nonzero(keep) < 18:
                return None
        points = points[keep]
        if np.ptp((points - a) @ direction) < length * .65:
            return None
        rails.append(points)
    return rails


def line_error(points):
    centered = points - points.mean(axis=0)
    _, _, vectors = np.linalg.svd(centered, full_matrices=False)
    return float(np.sqrt(np.mean((centered @ vectors[-1]) ** 2)))


def fit_lens(rails, width, height):
    """Accept only well-supported, invertible fits which improve held-out samples."""
    focal = float(max(width, height))
    matrix = np.array([[focal, 0, (width - 1) / 2], [0, focal, (height - 1) / 2], [0, 0, 1.]])

    def errors(k, subset=None):
        distortion = np.array([k, 0., 0., 0., 0.])
        result = []
        for rail in rails:
            points = rail if subset is None else rail[subset::2]
            corrected = cv2.undistortPointsIter(points.reshape(-1, 1, 2), matrix, distortion,
                None, matrix, (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 40, 1e-8))
            result.append(line_error(corrected[:, 0]))
        return np.array(result)

    baseline = errors(0)
    # Require curvature on two independent rails, not one shadow or pocket.
    threshold = max(.6, focal * .0008)
    if np.count_nonzero(baseline > threshold) < 2:
        return None
    candidates = np.linspace(-.75, .55, 53)
    scores = [np.mean(errors(float(k), 0)) for k in candidates]
    index = int(np.argmin(scores))
    if index in (0, len(candidates) - 1):
        return None
    fine = np.linspace(candidates[index - 1], candidates[index + 1], 21)
    k = float(min(fine, key=lambda value: np.mean(errors(float(value), 0))))
    if abs(k) < .015:
        return None
    after = errors(k)
    before_check, after_check = errors(0, 1), errors(k, 1)
    if (after.mean() > baseline.mean() * .65
            or baseline.mean() - after.mean() < focal * .0004
            or after.max() > max(1.5, focal * .0015)
            or np.any(after > baseline + focal * .00025)
            or after_check.mean() > before_check.mean() * .70
            or np.count_nonzero(after < baseline * .7) < 2):
        return None
    # Reject a folding radial map anywhere on this output image. For negative
    # k1 the radial derivative 1+3*k1*r^2 must remain positive at the corners.
    r2 = ((width - 1) ** 2 + (height - 1) ** 2) / (4 * focal ** 2)
    if 1 + 3 * k * r2 < .25:
        return None
    return LensCalibration(image_width=width, image_height=height,
                           camera_matrix=matrix.tolist(), distortion=[round(k, 6), 0, 0, 0, 0])


def estimate_table_lens(image, settings: Settings):
    """A curved coarse table is allowed here; normal detection is rerun after correction."""
    height, width = image.shape[:2]
    scale = min(1., 1000 / max(width, height))
    small = cv2.resize(image, None, fx=scale, fy=scale)
    observation = find_table(small, settings, allow_curved=True)
    if observation is None:
        return None
    h, w = small.shape[:2]
    corners = np.array([[p['x'] * (w - 1), p['y'] * (h - 1)] for p in observation['corners']])
    rails = rail_samples(observation['boundary'], corners, np.hypot(w, h))
    if rails is None:
        return None
    # Fit at source resolution so intrinsics and all acceptance tolerances agree.
    return fit_lens([rail / scale for rail in rails], width, height)
