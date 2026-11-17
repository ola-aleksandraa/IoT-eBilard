import io
import json
from datetime import datetime, timezone

import cv2
import numpy as np
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from app.config import ServerConfig
from app.main import create_app
from app.services.images import read_image
from tests.fixtures.synthetic import make_demo


@pytest.fixture
def application():
    return create_app(ServerConfig())


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


@pytest.fixture(scope="module")
def sample():
    return make_demo()


def capture(client, frame, options=None, endpoint="/api/v1/camera/detect"):
    """Serve `frame` as the next server-camera capture and call a camera route."""
    client.app.state.camera.capture = lambda: (frame.copy(), datetime.now(timezone.utc))
    return client.post(endpoint, json=options) if options is not None else client.post(endpoint)


def assert_numerical(body):
    forbidden = {"image", "images", "overlay", "rectified", "mask", "color", "pattern"}
    def visit(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value), value.keys()
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            assert not value.startswith("data:image/")
    visit(body)


def assert_layout(body):
    assert_numerical(body)
    assert body["table_status"] == "detected"
    detection = body["detection"]
    assert len(detection["balls"]) == detection["counts"]["total"] == 12
    assert detection["counts"] == {"total": 12, "cue": 1, "eight": 1, "solid": 7, "striped": 3, "unknown": 0}
    geometry = detection["geometry"]
    forward, inverse = np.array(geometry["source_to_table"]), np.array(geometry["table_to_source"])
    assert forward.shape == inverse.shape == (3, 3)
    assert np.allclose(forward @ inverse, np.eye(3), atol=1e-6)
    assert geometry["table_ratio"] == 2
    for ball in detection["balls"]:
        assert 0 <= ball["x"] <= 1 and 0 <= ball["y"] <= 1
        assert ball["radius"] == .026
        source = np.array([ball["source_x"] * (body["source"]["width"] - 1),
                           ball["source_y"] * (body["source"]["height"] - 1), 1])
        mapped = forward @ source
        assert mapped[:2] / mapped[2] == pytest.approx([ball["x"], ball["y"]], abs=.0001)
    assert body["schema_version"] == "1.0" and body["frame_id"]
    assert body["analysis_ms"] >= detection["processing_ms"] - .1


def test_docs_and_contract_expose_only_camera_routes(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/docs"
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/health").json()["engine"] == "OpenCV"
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health", "/api/v1/camera", "/api/v1/camera/calibrate", "/api/v1/camera/detect"}
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            assert set(operation["responses"]["200"]["content"]) == {"application/json"}, path
    for name in ("AnalysisOptions", "AnalysisResult", "Geometry", "Ball", "Counts", "Calibration", "LensCalibration"):
        assert name in schema["components"]["schemas"]
    assert "debug" not in schema["components"]["schemas"]["AnalysisOptions"]["properties"]
    assert "images" not in schema["components"]["schemas"]["Detection"]["properties"]


@pytest.mark.parametrize("path", ["images/detect", "images/calibrate", "settings", "categories", "shots",
                                  "shots/predict", "shots/simulate", "demo/detect", "demo/image", "demo/layout",
                                  "images/prepare", "images/layout", "camera/frame", "camera/layout", "ball-types"])
def test_upload_website_and_preview_routes_are_not_served_by_the_pi(client, path):
    assert client.get(f"/api/v1/{path}").status_code == 404
    assert client.post(f"/api/v1/{path}").status_code == 404


def test_actual_frame_analysis_never_encodes_pixels(client, sample, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime must never encode images")
    monkeypatch.setattr(cv2, "imencode", forbidden)
    response = capture(client, sample[0], {"client_frame_id": "frame-42"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert_layout(response.json())
    assert response.json()["client_frame_id"] == "frame-42"
    assert response.json()["source"]["kind"] == "camera"


def test_calibrate_then_detect_same_original_pixels(client, sample):
    calibration = capture(client, sample[0], {}, endpoint="/api/v1/camera/calibrate")
    assert calibration.status_code == 200
    body = calibration.json()
    assert_numerical(body)
    assert len(body["calibration"]["corners"]) == 4
    forward = np.array(body["geometry"]["source_to_table"])
    for corner, target in zip(body["calibration"]["corners"], [(0, 0), (1, 0), (1, 1), (0, 1)]):
        mapped = forward @ [corner["x"] * 1199, corner["y"] * 759, 1]
        assert mapped[:2] / mapped[2] == pytest.approx(target, abs=1e-6)
    result = capture(client, sample[0], {"calibration": body["calibration"]})
    assert result.status_code == 200
    assert_layout(result.json())


def test_manual_calibration_bypasses_finding_and_mismatch_recovers(client, sample, monkeypatch):
    def unexpected(*args):
        raise AssertionError("Must use manual calibration")
    monkeypatch.setattr("app.services.analysis.suggest_corners", unexpected)
    assert_layout(capture(client, sample[0], {"calibration": sample[1]}).json())
    bad = {**sample[1], "image_width": 640}
    assert capture(client, sample[0], {"calibration": bad}).status_code == 422
    assert capture(client, sample[0], {"calibration": sample[1]}).status_code == 200


def test_table_loss_clears_previous_positions(client, sample):
    assert_layout(capture(client, sample[0]).json())
    blank = np.full((760, 1200, 3), 100, np.uint8)
    result = capture(client, blank).json()
    assert result["table_status"] == "searching" and result["calibration"] is result["detection"] is None
    assert capture(client, blank, endpoint="/api/v1/camera/calibrate").json()["geometry"] is None
    assert_layout(capture(client, sample[0]).json())


def test_empty_manual_table_has_zero_counts(client):
    frame = np.full((500, 1000, 3), (100, 120, 25), np.uint8)
    corners = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]
    result = capture(client, frame, {"calibration": {"corners": corners, "image_width": 1000, "image_height": 500}}).json()
    assert result["table_status"] == "detected" and result["detection"]["counts"]["total"] == 0


@pytest.mark.parametrize("endpoint", ["camera/detect", "camera/calibrate"])
@pytest.mark.parametrize("body", ["not JSON", "[]", *[json.dumps(value) for value in [
    {"debug": True}, {"debug": False}, {"settings": {"ball_radius_ratio": -1}},
    {"settings": {"cloth_hue": 180}}, {"settings": {"table_ratio": float("nan")}},
    {"calibration": {}}, {"render": True},
]]])
def test_bad_and_old_debug_options_are_rejected_without_accessing_camera(client, application, monkeypatch, endpoint, body):
    monkeypatch.setattr(application.state.camera, "capture", lambda: pytest.fail("Camera must not open for invalid input"))
    response = client.post(f"/api/v1/{endpoint}", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_internal_lens_correction_and_matching_coordinate_space(client, sample):
    lens = {"image_width": 1200, "image_height": 760,
            "camera_matrix": [[1000, 0, 600], [0, 1000, 380], [0, 0, 1]], "distortion": [0] * 5}
    response = capture(client, sample[0], {"calibration": sample[1], "lens": lens})
    assert response.status_code == 200
    assert_layout(response.json())
    assert response.json()["source"]["lens_corrected"] is True
    assert response.json()["detection"]["geometry"]["source_space"] == "undistorted_oriented_pixels"
    assert capture(client, sample[0], {"lens": {**lens, "image_width": 640}}).status_code == 422
    assert capture(client, sample[0], {"lens": {**lens, "distortion": [0] * 6}}).status_code == 422


def test_heavy_routes_share_admission_control(client, application, sample):
    slot = application.state.processing_slot
    slot.acquire()
    try:
        for endpoint in ("camera/detect", "camera/calibrate"):
            response = capture(client, sample[0], endpoint=f"/api/v1/{endpoint}")
            assert response.status_code == 503
            assert response.headers["retry-after"] == "1"
        assert client.get("/health").status_code == client.get("/docs").status_code == 200
    finally:
        slot.release()
    assert capture(client, sample[0]).status_code == 200


def read(data: bytes):
    return read_image(UploadFile(file=io.BytesIO(data)))


def test_offline_reader_rejects_corrupt_oversize_and_unsupported_images(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        read(b"not an image")
    assert exc.value.status_code == 422
    for size, format, code in [((99, 100), "PNG", 422), ((100, 100), "GIF", 415),
                                ((10001, 100), "PNG", 413), ((4001, 4000), "PNG", 413)]:
        buffer = io.BytesIO()
        Image.new("RGB", size).save(buffer, format=format)
        with pytest.raises(HTTPException) as exc:
            read(buffer.getvalue())
        assert exc.value.status_code == code
    monkeypatch.setattr("app.services.images.MAX_UPLOAD_BYTES", 20)
    with pytest.raises(HTTPException) as exc:
        read(b"x" * 21)
    assert exc.value.status_code == 413


def test_offline_reader_applies_exif_orientation():
    image = Image.new("RGB", (320, 160), (30, 120, 100))
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    assert read(buffer.getvalue()).shape == (320, 160, 3)
