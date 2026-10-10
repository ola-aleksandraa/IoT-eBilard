import copy
import math

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.demo import DEMO_BALLS, make_demo
from app.models import Calibration, DetectionRequest, Settings
from app.vision import classify, detect, object_mask, split_component


def full_frame(width=1000, height=500):
    return {"corners": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}], "image_width": width, "image_height": height}


@pytest.mark.parametrize("brightness", [0.72, 1.0, 1.20])
def test_perspective_layout_localization_and_distractors(brightness):
    image, calibration = make_demo()
    image = np.uint8(np.clip(image.astype(float) * brightness, 0, 255))
    result = detect(image, DetectionRequest.model_validate({"calibration": calibration}))
    assert len(result["balls"]) == len(DEMO_BALLS), "Must neither detect pockets/cue nor miss balls."
    matched = set()
    for x, y, kind, _ in DEMO_BALLS:
        ball = min(result["balls"], key=lambda b: math.hypot(b["x"] * 999 - x, b["y"] * 499 - y))
        assert math.hypot(ball["x"] * 999 - x, ball["y"] * 499 - y) < 5
        assert ball["id"] not in matched
        matched.add(ball["id"])
        assert 0 <= ball["source_x"] <= 1 and 0 <= ball["source_y"] <= 1
        assert ball["kind"] in {kind, "unknown"}, "Prefer unknown over a wrong class."
    # Both touching centers are asserted above; Hough and watershed may each
    # supply the best outline. Watershed itself is tested independently below.


def test_touching_separation_independent_of_hough():
    mask = np.zeros((65, 100), np.uint8)
    cv2.circle(mask, (30, 30), 14, 255, -1)
    cv2.circle(mask, (57, 30), 14, 255, -1)
    found = sorted(split_component(mask, 13), key=lambda p: p[0])
    assert len(found) == 2
    assert found[0][0] == pytest.approx(30, abs=2)
    assert found[1][0] == pytest.approx(57, abs=2)


def test_empty_cloth_with_shadow_and_cue_returns_no_balls():
    image = np.full((500, 1000, 3), (100, 120, 25), np.uint8)
    cv2.ellipse(image, (450, 250), (100, 30), 0, 0, 360, (50, 60, 12), -1)
    cv2.line(image, (20, 120), (290, 190), (140, 180, 200), 6)
    result = detect(image, DetectionRequest.model_validate({"calibration": full_frame()}))
    assert result["balls"] == []
    assert "No balls" in result["warnings"][0]


@pytest.mark.parametrize("kind,color", [("cue", (235, 235, 235)), ("eight", (22, 22, 22)), ("solid", (20, 40, 220)), ("unknown", (110, 110, 110))])
def test_classification_rules_have_explicit_unknown(kind, color):
    image = np.full((80, 80, 3), (100, 120, 25), np.uint8)
    cv2.circle(image, (40, 40), 20, color, -1)
    if kind in ("eight", "solid"):
        cv2.circle(image, (40, 40), 5, (235, 235, 235), -1)
    assert classify(image, 40, 40, 20)[0] == kind


def test_white_caps_differ_from_number_patch():
    image = np.full((80, 80, 3), (100, 120, 25), np.uint8)
    cv2.circle(image, (40, 40), 20, (25, 45, 220), -1)
    yy, xx = np.mgrid[:80, :80]
    image[((xx - 40)**2 + (yy - 40)**2 < 20**2) & (np.abs(yy - 40) > 7)] = 235
    assert classify(image, 40, 40, 20)[0] == "striped"


def test_hue_wraparound_removes_red_cloth():
    hsv = np.full((100, 100, 3), (179, 190, 140), np.uint8)
    hsv[:, 50:, 0] = 1
    image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    mask, _ = object_mask(image, Settings(cloth_hue=0))
    assert np.count_nonzero(mask) == 0


@pytest.mark.parametrize("indexes", [[0, 2, 1, 3], [0, 3, 2, 1], [0, 0, 2, 3]])
def test_invalid_corner_order_is_rejected(indexes):
    calibration = full_frame()
    calibration["corners"] = [calibration["corners"][i] for i in indexes]
    with pytest.raises(ValidationError):
        Calibration.model_validate(calibration)


def test_calibration_resolution_mismatch_is_rejected():
    image, calibration = make_demo()
    mismatch = copy.deepcopy(calibration)
    mismatch["image_width"] = 640
    with pytest.raises(ValueError, match="resolution differs"):
        detect(image, DetectionRequest.model_validate({"calibration": mismatch}))


def test_mapping_back_to_source_matches_homography():
    image, calibration = make_demo()
    result = detect(image, DetectionRequest.model_validate({"calibration": calibration}))
    matrix = np.array(result["homography"])
    for ball in result["balls"]:
        source = np.float32([[[ball["source_x"] * 1199, ball["source_y"] * 759]]])
        x, y = cv2.perspectiveTransform(source, matrix)[0, 0]
        assert x / 999 == pytest.approx(ball["x"], abs=0.0001)
        assert y / 499 == pytest.approx(ball["y"], abs=0.0001)
