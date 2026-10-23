"""On-demand capture, with deterministic device release on every request."""

from datetime import datetime, timezone

import cv2
from fastapi import HTTPException

from ..config import ServerConfig
from .images import validate_dimensions


class Camera:
    def __init__(self, config: ServerConfig):
        self.config = config

    def status(self):
        source = self.config.camera_source
        source_kind = "device" if isinstance(source, int) else "stream" if "://" in source else "file"
        return {
            "source_kind": source_kind,
            "device_index": source if isinstance(source, int) else None,
            "requested_width": self.config.camera_width,
            "requested_height": self.config.camera_height,
            "warmup_frames": self.config.camera_warmup_frames,
            "note": "Capture opens and releases the source per request. Availability is checked by capture. "
                    "The server's camera is used; source URLs and credentials are never returned.",
        }

    def capture(self):
        source = self.config.camera_source
        capture = None
        try:
            if isinstance(source, int):
                capture = cv2.VideoCapture(source)
            else:
                # FFmpeg accepts these open-only timeout parameters for network
                # streams. Files also use this path for reproducible validation.
                capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.camera_timeout_ms,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.config.camera_timeout_ms,
                ])
            if not capture.isOpened():
                raise HTTPException(503, "Camera unavailable. Check CAMERA_SOURCE, permissions and connection.")
            if isinstance(source, int):
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera_width)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera_height)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Discard startup frames for camera exposure. Reopening avoids a
            # persistent unread capture queue returning old layouts after idle.
            for _ in range(self.config.camera_warmup_frames):
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    raise HTTPException(503, "Camera returned no frame. Check the source or reconnect it.")
            captured_at = datetime.now(timezone.utc)
            validate_dimensions(frame.shape[1], frame.shape[0])
            return frame, captured_at
        except cv2.error:
            raise HTTPException(503, "Camera capture failed. Check the source and OpenCV video backend.") from None
        finally:
            if capture is not None:
                capture.release()
