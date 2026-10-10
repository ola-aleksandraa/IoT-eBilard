"""Regression cases for broadcast casts, number patches and table-level rules."""

import cv2
import numpy as np
import pytest

from app.classification import PALETTE, classify, enforce_unique_specials, white_balance
from app.localization import orient_corners
from app.models import DetectionRequest
from app.vision import detect


def ball_image(color=(35, 55, 220)):
    image = np.full((120, 120, 3), (150, 110, 40), np.uint8)
    cv2.circle(image, (60, 60), 35, color, -1)
    return image


@pytest.mark.parametrize("angle", [0, 35, 90, 145])
def test_stripe_pattern_is_rotation_invariant(angle):
    image = ball_image()
    yy, xx = np.mgrid[:120, :120]
    distance = (xx - 60) * np.sin(np.deg2rad(angle)) + (yy - 60) * np.cos(
        np.deg2rad(angle)
    )
    image[((xx - 60) ** 2 + (yy - 60) ** 2 < 35**2) & (np.abs(distance) > 12)] = 235
    assert classify(image, 60, 60, 35)[0] == "striped"


@pytest.mark.parametrize("offset", [(0, 0), (0, -14), (12, 9)])
def test_small_white_number_patch_is_still_full(offset):
    image = ball_image()
    cv2.circle(image, (60 + offset[0], 60 + offset[1]), 8, (230, 230, 230), -1)
    cv2.circle(image, (60 + offset[0], 60 + offset[1]), 2, (30, 30, 30), -1)
    assert classify(image, 60, 60, 35)[0] == "solid"


def test_warm_cast_and_small_cue_spots():
    image = ball_image((190, 224, 242))
    for point in [(50, 56), (67, 69)]:
        cv2.circle(image, point, 2, (35, 40, 180), -1)
    assert classify(image, 60, 60, 35, white_balance(image))[0] == "cue"


def test_black_with_number_patch_and_highlight():
    image = ball_image((37, 30, 26))
    cv2.circle(image, (60, 46), 9, (218, 218, 218), -1)
    cv2.circle(image, (48, 40), 3, (245, 245, 245), -1)
    assert classify(image, 60, 60, 35)[0] == "eight"


def test_unique_special_types_preserve_all_centers_and_never_invent_balls():
    balls = [
        {
            "id": i,
            "kind": kind,
            "confidence": score,
            "white_fraction": white,
            "x": i / 10,
            "y": 0.5,
        }
        for i, (kind, score, white) in enumerate(
            [
                ("cue", 0.95, 0.97),
                ("cue", 0.80, 0.81),
                ("eight", 0.91, 0.1),
                ("eight", 0.75, 0.1),
                ("solid", 0.76, 0.1),
            ],
            1,
        )
    ]
    result = enforce_unique_specials(balls)
    assert len(result) == 5
    assert [b["x"] for b in result] == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert [b["kind"] for b in result] == [
        "cue",
        "unknown",
        "eight",
        "unknown",
        "solid",
    ]
    assert enforce_unique_specials([]) == []
    assert enforce_unique_specials([{"id": 1, "kind": "solid"}])[0]["kind"] == "solid"


def test_palette_encodes_only_category():
    assert classify(ball_image((20, 30, 230)), 60, 60, 35)[3] == PALETTE["solid"]
    assert classify(ball_image((30, 190, 30)), 60, 60, 35)[3] == PALETTE["solid"]
    assert PALETTE["solid"] == PALETTE["striped"]


def test_ball_next_to_corner_is_not_rejected_as_a_pocket():
    image = np.full((500, 1000, 3), (145, 100, 30), np.uint8)
    cv2.circle(image, (17, 17), 13, (235, 235, 235), -1)
    calibration = {
        "image_width": 1000,
        "image_height": 500,
        "corners": [
            {"x": 0, "y": 0},
            {"x": 1, "y": 0},
            {"x": 1, "y": 1},
            {"x": 0, "y": 1},
        ],
    }
    found = detect(
        image,
        DetectionRequest.model_validate({"calibration": calibration}),
        debug=False,
    )["balls"]
    assert len(found) == 1
    assert abs(found[0]["x"] - 0.017) < 0.005
    assert abs(found[0]["y"] - 0.034) < 0.01


def test_end_on_view_maps_the_long_edge_to_canvas_width():
    image = np.zeros((800, 1000, 3), np.uint8)
    corners = [
        {"x": 0.35, "y": 0.20},
        {"x": 0.65, "y": 0.20},
        {"x": 0.82, "y": 0.81},
        {"x": 0.18, "y": 0.81},
    ]
    ordered = orient_corners(image, corners)
    assert ordered == corners[1:] + corners[:1]
    overhead = [
        {"x": 0.1, "y": 0.2},
        {"x": 0.9, "y": 0.2},
        {"x": 0.9, "y": 0.7},
        {"x": 0.1, "y": 0.7},
    ]
    assert orient_corners(image, overhead) == overhead


def test_round_camera_silhouettes_survive_strong_end_on_perspective():
    image = np.full((800, 1000, 3), (25, 25, 25), np.uint8)
    points = np.float32([[650, 160], [820, 650], [180, 650], [350, 160]])
    cv2.fillConvexPoly(image, points.astype(np.int32), (150, 100, 30))
    expected = [(500, 240, 9, (235, 235, 235)), (475, 400, 12, (20, 20, 20)),
                (625, 480, 13, (30, 50, 220)), (400, 560, 15, (20, 160, 30))]
    for x, y, radius, color in expected:
        cv2.circle(image, (x, y), radius, color, -1)
    calibration = {"image_width": 1000, "image_height": 800,
                   "corners": [{"x": float(x/999), "y": float(y/799)} for x, y in points]}
    result = detect(image, DetectionRequest.model_validate({"calibration": calibration}), debug=False)
    assert len(result["balls"]) == len(expected)
    for x, y, _, _ in expected:
        assert min(np.hypot(b["source_x"]*999-x, b["source_y"]*799-y) for b in result["balls"]) < 3
    assert all(0 <= b["x"] <= 1 and 0 <= b["y"] <= 1 for b in result["balls"])
