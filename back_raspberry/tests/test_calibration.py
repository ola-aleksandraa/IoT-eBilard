import cv2
import numpy as np
import pytest

from app.engine.calibration import find_table
from app.engine.models import Settings
from app.engine.vision import object_mask


@pytest.mark.parametrize("corners", [
    [[80, 100], [700, 130], [750, 500], [50, 490]],
    [[290, 130], [540, 130], [740, 540], [80, 540]],
    [[140, 60], [710, 150], [650, 540], [90, 380]],
])
@pytest.mark.parametrize("cloth", [(140, 100, 20), (90, 140, 30), (175, 175, 175)])
def test_corner_intersections_ignore_pockets_and_support_perspective(corners, cloth):
    expected = np.float32(corners)
    image = np.full((600, 800, 3), 25, np.uint8)
    cv2.fillConvexPoly(image, np.int32(expected), cloth)
    # Corners are intersections of the rails, not the visible pocket cut-outs.
    for point in expected:
        cv2.circle(image, tuple(point.astype(int)), 14, (20, 20, 20), -1)
    cv2.circle(image, (390, 290), 12, (245, 245, 245), -1)
    cv2.circle(image, (460, 340), 12, (20, 30, 230), -1)
    found = find_table(image)
    assert found is not None
    actual = np.array([[p["x"] * 799, p["y"] * 599] for p in found["corners"]])
    assert np.linalg.norm(actual - expected, axis=1).max() < 3


def test_neutral_cloth_segmentation_keeps_ball_contrast():
    image = np.full((200, 400, 3), 160, np.uint8)
    cv2.circle(image, (100, 100), 10, (235, 235, 235), -1)
    cv2.circle(image, (200, 100), 10, (20, 20, 20), -1)
    cv2.circle(image, (300, 100), 10, (20, 30, 220), -1)
    mask, hue = object_mask(image, Settings())
    assert hue is None
    assert mask[50, 50] == 0
    assert all(mask[100, x] == 255 for x in [100, 200, 300])


def test_featureless_frame_has_no_table():
    assert find_table(np.full((600, 800, 3), 150, np.uint8)) is None
