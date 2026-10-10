import base64
import io
import json

import cv2
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.demo import make_demo
from app.main import app

client = TestClient(app)


@pytest.fixture
def demo():
    image, calibration = make_demo()
    return cv2.imencode(".png", image)[1].tobytes(), calibration


def test_health_and_demo_are_available():
    assert client.get("/api/health").json()["engine"] == "OpenCV"
    demo = client.get("/api/demo").json()
    assert demo["synthetic"] is True and demo["expected_count"] == 12


def test_complete_prepare_detect_roundtrip(demo):
    data, calibration = demo
    prepared = client.post("/api/prepare", files={"file": ("table.png", data, "image/png")})
    assert prepared.status_code == 200
    body = prepared.json()
    assert len(body["suggested_corners"]) == 4
    canonical = base64.b64decode(body["image"].split(",")[1])
    detected = client.post("/api/detect", files={"file": ("frame.png", canonical, "image/png")}, data={"config": json.dumps({"calibration": calibration})})
    assert detected.status_code == 200
    assert len(detected.json()["balls"]) == 12
    assert set(detected.json()["images"]) == {"rectified", "mask", "overlay"}


@pytest.mark.parametrize("config", ["not json", "{}", '{"calibration": null}', '{"calibration":{},"settings":{"ball_radius_ratio":-1}}'])
def test_bad_config_returns_readable_422(demo, config):
    response = client.post("/api/detect", files={"file": ("frame.png", demo[0])}, data={"config": config})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_corrupted_image_returns_422():
    response = client.post("/api/prepare", files={"file": ("fake.png", b"not an image")})
    assert response.status_code == 422


def test_exif_orientation_is_normalized():
    image = Image.new("RGB", (320, 160), (30, 120, 100))
    exif = Image.Exif(); exif[274] = 6
    buffer = io.BytesIO(); image.save(buffer, format="JPEG", exif=exif)
    response = client.post("/api/prepare", files={"file": ("rotated.jpg", buffer.getvalue())})
    assert response.status_code == 200
    assert (response.json()["width"], response.json()["height"]) == (160, 320)


def test_lens_correction_requires_matching_resolution(demo):
    lens = {"image_width": 640, "image_height": 480, "camera_matrix": [[600, 0, 320], [0, 600, 240], [0, 0, 1]], "distortion": [0, 0, 0, 0, 0]}
    response = client.post("/api/prepare", files={"file": ("frame.png", demo[0])}, data={"lens": json.dumps(lens)})
    assert response.status_code == 422
    assert "resolution" in response.json()["detail"]


def test_zero_lens_distortion_preserves_pixels(demo):
    lens = {"image_width": 1200, "image_height": 760, "camera_matrix": [[1000, 0, 600], [0, 1000, 380], [0, 0, 1]], "distortion": [0, 0, 0, 0, 0]}
    response = client.post("/api/prepare", files={"file": ("frame.png", demo[0])}, data={"lens": json.dumps(lens)})
    assert response.status_code == 200
    assert response.json()["lens_corrected"] is True
    assert base64.b64decode(response.json()["image"].split(",")[1]) == demo[0]


def test_invalid_lens_shape_returns_422(demo):
    lens = {"image_width": 1200, "image_height": 760, "camera_matrix": [[1, 0], [0, 1]], "distortion": [0, 0, 0, 0]}
    response = client.post("/api/prepare", files={"file": ("frame.png", demo[0])}, data={"lens": json.dumps(lens)})
    assert response.status_code == 422


def test_live_automatically_finds_table_and_balls(demo):
    response = client.post("/api/live", files={"file": ("live.png", demo[0])})
    assert response.status_code == 200
    body = response.json()
    assert body["table_status"] == "detected"
    assert len(body["calibration"]["corners"]) == 4
    assert len(body["detection"]["balls"]) == 12
    assert body["detection"]["images"] is None, "Live responses should not transfer debug images."


def test_live_loss_and_reacquisition_never_reuses_old_positions(demo):
    client.post("/api/live", files={"file": ("live.png", demo[0])})
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 760), (100, 100, 100)).save(buffer, format="PNG")
    missing = client.post("/api/live", files={"file": ("blank.png", buffer.getvalue())}).json()
    assert missing == {"table_status": "searching", "calibration": None, "detection": None}
    recovered = client.post("/api/live", files={"file": ("live.png", demo[0])}).json()
    assert recovered["table_status"] == "detected"
    assert len(recovered["detection"]["balls"]) == 12


def test_live_manual_corners_and_resolution_validation(demo):
    config = {"calibration": demo[1]}
    response = client.post("/api/live", files={"file": ("live.png", demo[0])}, data={"config": json.dumps(config)})
    assert response.status_code == 200
    assert response.json()["calibration"] == demo[1]
    config["calibration"]["image_width"] = 640
    mismatch = client.post("/api/live", files={"file": ("live.png", demo[0])}, data={"config": json.dumps(config)})
    assert mismatch.status_code == 422


def test_locked_calibration_bypasses_corner_finding(demo, monkeypatch):
    def unexpected_recalibration(*args, **kwargs):
        raise AssertionError("A fixed camera must not estimate new corners.")
    monkeypatch.setattr("app.main.suggest_corners", unexpected_recalibration)
    response = client.post("/api/live", files={"file": ("live.png", demo[0])},
                           data={"config": json.dumps({"calibration": demo[1]})})
    assert response.status_code == 200
    assert response.json()["calibration"] == demo[1]
    assert len(response.json()["detection"]["balls"]) == 12
