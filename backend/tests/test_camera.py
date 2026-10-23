import cv2
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import ServerConfig
from tests.fixtures.synthetic import make_demo
from app.main import create_app
from app.services.camera import Camera


class FakeCapture:
    def __init__(self, *, opened=True, readable=True):
        self.opened = opened
        self.readable = readable
        self.released = False
        self.reads = 0

    def isOpened(self):
        return self.opened

    def set(self, *args):
        return True

    def read(self):
        self.reads += 1
        return self.readable, make_demo()[0] if self.readable else None

    def release(self):
        self.released = True


@pytest.mark.parametrize("opened,readable,success", [(True, True, True), (False, True, False), (True, False, False)])
def test_capture_always_releases_device(monkeypatch, opened, readable, success):
    capture = FakeCapture(opened=opened, readable=readable)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: capture)
    camera = Camera(ServerConfig())
    if success:
        frame, captured_at = camera.capture()
        assert frame.shape == (760, 1200, 3)
        assert captured_at.tzinfo is not None
        assert capture.reads == 3
    else:
        with pytest.raises(HTTPException) as exc:
            camera.capture()
        assert exc.value.status_code == 503
    assert capture.released


def test_camera_endpoint_errors_and_recovery(monkeypatch):
    captures = []
    def factory(*args):
        capture = FakeCapture(readable=bool(captures))
        captures.append(capture)
        return capture
    monkeypatch.setattr(cv2, "VideoCapture", factory)
    with TestClient(create_app(ServerConfig())) as client:
        assert client.get("/api/v1/camera").json()["device_index"] == 0
        assert not captures, "Status must not activate the camera"
        assert client.post("/api/v1/camera/detect", json={}).status_code == 503
        result = client.post("/api/v1/camera/detect", json={})
        assert result.status_code == 200
        assert result.json()["source"]["kind"] == "camera"
        assert result.json()["detection"]["counts"]["total"] == 12
        calibration = client.post("/api/v1/camera/calibrate", json={})
        assert calibration.status_code == 200
        assert len(calibration.json()["calibration"]["corners"]) == 4
        assert calibration.headers["content-type"] == "application/json"
    assert all(capture.released for capture in captures)


def test_camera_backend_exception_is_retryable_and_released(monkeypatch):
    capture = FakeCapture()
    def fail():
        raise cv2.error("read failed")
    capture.read = fail
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: capture)
    with pytest.raises(HTTPException) as exc:
        Camera(ServerConfig()).capture()
    assert exc.value.status_code == 503
    assert capture.released


def test_actual_opencv_video_capture_and_detection(tmp_path):
    """Exercise real VideoCapture, not just mocks, using a generated local clip."""
    path = tmp_path / "camera.avi"
    frame = make_demo()[0]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (1200, 760))
    assert writer.isOpened()
    try:
        for _ in range(5):
            writer.write(frame)
    finally:
        writer.release()
    with TestClient(create_app(ServerConfig(camera_source=str(path)))) as client:
        result = client.post("/api/v1/camera/detect", json={})
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["table_status"] == "detected"
        assert body["detection"]["counts"]["total"] == 12
        assert body["source"]["width"] == 1200
        # Each request starts a fresh capture and releases the source.
        assert client.post("/api/v1/camera/detect").status_code == 200


def test_nonexistent_video_returns_503(tmp_path):
    with TestClient(create_app(ServerConfig(camera_source=str(tmp_path / "absent.avi")))) as client:
        assert client.post("/api/v1/camera/detect").status_code == 503


def test_camera_source_credentials_are_not_disclosed():
    camera = Camera(ServerConfig(camera_source="rtsp://user:secret@example.invalid/video"))
    assert camera.status()["source_kind"] == "stream"
    assert "secret" not in str(camera.status())


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("CAMERA_SOURCE", "2")
    monkeypatch.setenv("CAMERA_WIDTH", "1920")
    monkeypatch.setenv("CAMERA_HEIGHT", "1080")
    config = ServerConfig.from_env()
    assert config.camera_source == 2
    assert config.camera_width == 1920
    monkeypatch.setenv("CAMERA_SOURCE", "-1")
    with pytest.raises(ValueError):
        ServerConfig.from_env()


@pytest.mark.parametrize("kwargs", [{"camera_source": -1}, {"camera_source": ""},
    {"camera_warmup_frames": 0}, {"camera_timeout_ms": -1}, {"camera_width": 1},
    {"camera_width": 5000, "camera_height": 5000}, {"opencv_threads": 0}])
def test_invalid_server_configuration_fails_early(kwargs):
    with pytest.raises(ValueError):
        ServerConfig(**kwargs)
