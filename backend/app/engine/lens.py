"""Point mappings for native-pixel recognition and corrected table geometry."""

import cv2
import numpy as np


def undistort_points(points, lens):
    points = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    if lens is None:
        return points[:, 0]
    matrix = np.float64(lens.camera_matrix)
    return cv2.undistortPointsIter(points, matrix, np.float64(lens.distortion), None, matrix,
        (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 60, 1e-8))[:, 0]


def distort_points(points, lens):
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if lens is None:
        return points
    matrix = np.float64(lens.camera_matrix)
    normalized = (points - matrix[:2, 2]) / matrix.diagonal()[:2]
    xyz = np.column_stack([normalized, np.ones(len(points))])
    return cv2.projectPoints(xyz, np.zeros(3), np.zeros(3), matrix, np.float64(lens.distortion))[0][:, 0]


def source_outline(corners, lens):
    if lens is None:
        return corners
    samples = np.concatenate([a + np.linspace(0, 1, 24, endpoint=False)[:, None] * (b - a)
                              for a, b in zip(corners, np.roll(corners, -1, axis=0))])
    return distort_points(samples, lens)
