import io
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import ServerConfig
from app.main import create_app
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
    image, calibration = make_demo()
    return cv2.imencode(".png", image)[1].tobytes(), calibration


def upload(client, data, config=None, endpoint="/api/v1/images/detect"):
    return client.post(endpoint, files={"file": ("table.png", data, "image/png")},
                       data={"config": json.dumps(config)} if config is not None else {})


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


def test_docs_and_contract_expose_only_numerical_application_routes(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/docs"
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/health").json()["engine"] == "OpenCV"
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health", "/api/v1/settings", "/api/v1/categories", "/api/v1/images/calibrate",
        "/api/v1/images/detect", "/api/v1/camera", "/api/v1/camera/calibrate", "/api/v1/camera/detect", "/api/v1/shots", "/api/v1/shots/predict", "/api/v1/shots/simulate"}
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            assert set(operation["responses"]["200"]["content"]) == {"application/json"}, path
    for name in ("AnalysisOptions", "AnalysisResult", "Geometry", "Ball", "Counts", "Calibration", "LensCalibration"):
        assert name in schema["components"]["schemas"]
    assert "debug" not in schema["components"]["schemas"]["AnalysisOptions"]["properties"]
    assert "images" not in schema["components"]["schemas"]["Detection"]["properties"]


@pytest.mark.parametrize("path", ["demo/detect", "demo/image", "demo/layout", "images/prepare", "images/layout", "camera/frame", "camera/layout", "ball-types"])
def test_removed_preview_and_demo_endpoints_cannot_return_images(client, path):
    assert client.get(f"/api/v1/{path}").status_code == 404
    assert client.post(f"/api/v1/{path}").status_code == 404


def test_categories_and_defaults_have_no_presentation_dependency(client):
    assert client.get("/api/v1/settings").json()["split_touching"] is True
    response = client.get("/api/v1/categories")
    assert {item["kind"] for item in response.json()} == {"cue", "eight", "solid", "striped", "unknown"}
    assert_numerical(response.json())


def test_actual_image_analysis_never_encodes_pixels(client, sample, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime must never encode images")
    monkeypatch.setattr(cv2, "imencode", forbidden)
    response = upload(client, sample[0], {"client_frame_id": "frame-42"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert_layout(response.json())
    assert response.json()["client_frame_id"] == "frame-42"


def test_calibrate_then_detect_same_original_pixels(client, sample):
    calibration = upload(client, sample[0], endpoint="/api/v1/images/calibrate")
    assert calibration.status_code == 200
    body = calibration.json()
    assert_numerical(body)
    assert len(body["calibration"]["corners"]) == 4
    forward = np.array(body["geometry"]["source_to_table"])
    for corner, target in zip(body["calibration"]["corners"], [(0, 0), (1, 0), (1, 1), (0, 1)]):
        mapped = forward @ [corner["x"] * 1199, corner["y"] * 759, 1]
        assert mapped[:2] / mapped[2] == pytest.approx(target, abs=1e-6)
    result = upload(client, sample[0], {"calibration": body["calibration"]})
    assert result.status_code == 200
    assert_layout(result.json())


def test_manual_calibration_bypasses_finding_and_mismatch_recovers(client, sample, monkeypatch):
    def unexpected(*args):
        raise AssertionError("Must use manual calibration")
    monkeypatch.setattr("app.services.analysis.suggest_corners", unexpected)
    assert_layout(upload(client, sample[0], {"calibration": sample[1]}).json())
    bad = {**sample[1], "image_width": 640}
    assert upload(client, sample[0], {"calibration": bad}).status_code == 422
    assert upload(client, sample[0], {"calibration": sample[1]}).status_code == 200


def test_table_loss_clears_previous_positions(client, sample):
    assert_layout(upload(client, sample[0]).json())
    blank = cv2.imencode(".png", np.full((760, 1200, 3), 100, np.uint8))[1].tobytes()
    result = upload(client, blank).json()
    assert result["table_status"] == "searching" and result["calibration"] is result["detection"] is None
    assert upload(client, blank, endpoint="/api/v1/images/calibrate").json()["geometry"] is None
    assert_layout(upload(client, sample[0]).json())


def test_empty_manual_table_has_zero_counts(client):
    frame = cv2.imencode(".png", np.full((500, 1000, 3), (100, 120, 25), np.uint8))[1].tobytes()
    corners = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]
    result = upload(client, frame, {"calibration": {"corners": corners, "image_width": 1000, "image_height": 500}}).json()
    assert result["table_status"] == "detected" and result["detection"]["counts"]["total"] == 0


@pytest.mark.parametrize("config", ["not JSON", "null", "[]", *[json.dumps(value) for value in [
    {"debug": True}, {"debug": False}, {"settings": {"ball_radius_ratio": -1}},
    {"settings": {"cloth_hue": 180}}, {"settings": {"table_ratio": float("nan")}},
    {"calibration": {}}, {"render": True},
]]])
def test_bad_and_old_debug_options_are_rejected(client, sample, config):
    response = client.post("/api/v1/images/detect", files={"file": ("table.png", sample[0])}, data={"config": config})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_camera_body_rejects_debug_without_accessing_camera(client, application, monkeypatch):
    monkeypatch.setattr(application.state.camera, "capture", lambda: pytest.fail("Camera must not open for invalid input"))
    assert client.post("/api/v1/camera/detect", json={"debug": True}).status_code == 422


def test_nonfinite_camera_options_return_json_error_instead_of_500(client):
    response = client.post("/api/v1/camera/detect", content=json.dumps({"settings": {"table_ratio": float("nan")}}),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_missing_corrupt_oversize_and_unsupported_images(client, monkeypatch):
    assert client.post("/api/v1/images/detect").status_code == 422
    assert upload(client, b"not an image").status_code == 422
    for size, format, code in [((99, 100), "PNG", 422), ((100, 100), "GIF", 415),
                                ((10001, 100), "PNG", 413), ((4001, 4000), "PNG", 413)]:
        buffer = io.BytesIO()
        Image.new("RGB", size).save(buffer, format=format)
        assert upload(client, buffer.getvalue()).status_code == code
    monkeypatch.setattr("app.services.images.MAX_UPLOAD_BYTES", 20)
    assert upload(client, b"x" * 21).status_code == 413


def test_exif_orientation_is_reported_without_returning_image(client):
    image = Image.new("RGB", (320, 160), (30, 120, 100))
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    response = upload(client, buffer.getvalue(), endpoint="/api/v1/images/calibrate")
    assert response.status_code == 200
    assert (response.json()["source"]["width"], response.json()["source"]["height"]) == (160, 320)
    assert_numerical(response.json())


def test_internal_lens_correction_and_matching_coordinate_space(client, sample):
    lens = {"image_width": 1200, "image_height": 760,
            "camera_matrix": [[1000, 0, 600], [0, 1000, 380], [0, 0, 1]], "distortion": [0] * 5}
    response = upload(client, sample[0], {"calibration": sample[1], "lens": lens})
    assert response.status_code == 200
    assert_layout(response.json())
    assert response.json()["source"]["lens_corrected"] is True
    assert response.json()["detection"]["geometry"]["source_space"] == "undistorted_oriented_pixels"
    assert upload(client, sample[0], {"lens": {**lens, "image_width": 640}}).status_code == 422
    assert upload(client, sample[0], {"lens": {**lens, "distortion": [0] * 6}}).status_code == 422


def test_heavy_routes_share_admission_control(client, application, sample):
    slot = application.state.processing_slot
    slot.acquire()
    try:
        for endpoint in ("images/detect", "images/calibrate", "camera/detect", "camera/calibrate"):
            response = client.post(f"/api/v1/{endpoint}",
                **({"files": {"file": ("table.png", sample[0])}} if endpoint.startswith("images/") else {}))
            assert response.status_code == 503
            assert response.headers["retry-after"] == "1"
        assert client.get("/health").status_code == client.get("/docs").status_code == 200
    finally:
        slot.release()
    assert upload(client, sample[0]).status_code == 200
