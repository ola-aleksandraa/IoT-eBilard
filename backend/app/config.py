"""Server configuration. Camera sources are selected by the server operator."""

import os
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class ServerConfig:
    camera_source: Union[int, str] = 0
    camera_width: int = 1280
    camera_height: int = 960
    camera_warmup_frames: int = 3
    camera_timeout_ms: int = 5000
    opencv_threads: int = 4

    def __post_init__(self):
        if isinstance(self.camera_source, int) and self.camera_source < 0:
            raise ValueError("CAMERA_SOURCE device index must be non-negative.")
        if not str(self.camera_source).strip():
            raise ValueError("CAMERA_SOURCE cannot be empty.")
        if not (100 <= self.camera_width <= 10000 and 100 <= self.camera_height <= 10000):
            raise ValueError("Camera dimensions must be between 100 and 10000.")
        if self.camera_width * self.camera_height > 16_000_000:
            raise ValueError("Camera dimensions must not exceed 16 megapixels.")
        if not 1 <= self.camera_warmup_frames <= 30:
            raise ValueError("CAMERA_WARMUP_FRAMES must be between 1 and 30.")
        if not 100 <= self.camera_timeout_ms <= 60000:
            raise ValueError("CAMERA_TIMEOUT_MS must be between 100 and 60000.")
        if not 1 <= self.opencv_threads <= 16:
            raise ValueError("OPENCV_THREADS must be between 1 and 16.")

    @classmethod
    def from_env(cls):
        source = os.getenv("CAMERA_SOURCE", "0")
        return cls(
            camera_source=int(source) if source.lstrip("-").isdigit() else source,
            camera_width=int(os.getenv("CAMERA_WIDTH", "1280")),
            camera_height=int(os.getenv("CAMERA_HEIGHT", "960")),
            camera_warmup_frames=int(os.getenv("CAMERA_WARMUP_FRAMES", "3")),
            camera_timeout_ms=int(os.getenv("CAMERA_TIMEOUT_MS", "5000")),
            opencv_threads=int(os.getenv("OPENCV_THREADS", "4")),
        )
