"""Watcher configuration from environment variables."""

import os
from dataclasses import dataclass

from .stability import StabilityConfig


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WatchConfig:
    enabled: bool = False
    pi_url: str = "http://127.0.0.1:8002"
    pi_timeout_s: float = 15.0
    interval_ms: int = 1000
    table_width_cm: float = 127.0   # short side, across the table
    table_length_cm: float = 254.0  # long side, along the table
    ball_radius_ratio: float = 0.026
    window: int = 4
    move_eps: float = 0.015
    still_eps: float = 0.006
    change_confirm: int = 2
    recalibrate_after: int = 5      # consecutive "searching"/failed frames before recalibrating

    def __post_init__(self):
        if self.table_width_cm <= 0 or self.table_length_cm <= 0:
            raise ValueError("TABLE_WIDTH_CM and TABLE_LENGTH_CM must be positive.")
        if not 1 <= self.table_ratio <= 3:
            raise ValueError("TABLE_LENGTH_CM / TABLE_WIDTH_CM must be between 1 and 3.")
        if not 50 <= self.interval_ms <= 60_000:
            raise ValueError("WATCH_INTERVAL_MS must be between 50 and 60000.")
        if self.recalibrate_after < 1:
            raise ValueError("WATCH_RECALIBRATE_AFTER must be at least 1.")
        self.stability  # validates the window parameters

    @property
    def table_ratio(self) -> float:
        """Matches back_raspberry Settings.table_ratio: cloth width (long, x) / height (short, y)."""
        return self.table_length_cm / self.table_width_cm

    @property
    def stability(self) -> StabilityConfig:
        return StabilityConfig(window=self.window, move_eps=self.move_eps, still_eps=self.still_eps,
                               change_confirm=self.change_confirm, table_ratio=self.table_ratio)

    @property
    def pi_settings(self) -> dict:
        return {"table_ratio": self.table_ratio, "ball_radius_ratio": self.ball_radius_ratio}

    @classmethod
    def from_env(cls) -> "WatchConfig":
        return cls(
            enabled=_flag("TABLE_WATCH_ENABLED"),
            pi_url=os.getenv("PI_URL", cls.pi_url).rstrip("/"),
            pi_timeout_s=float(os.getenv("PI_TIMEOUT_S", cls.pi_timeout_s)),
            interval_ms=int(os.getenv("WATCH_INTERVAL_MS", cls.interval_ms)),
            table_width_cm=float(os.getenv("TABLE_WIDTH_CM", cls.table_width_cm)),
            table_length_cm=float(os.getenv("TABLE_LENGTH_CM", cls.table_length_cm)),
            ball_radius_ratio=float(os.getenv("WATCH_BALL_RADIUS_RATIO", cls.ball_radius_ratio)),
            window=int(os.getenv("WATCH_WINDOW", cls.window)),
            move_eps=float(os.getenv("WATCH_MOVE_EPS", cls.move_eps)),
            still_eps=float(os.getenv("WATCH_STILL_EPS", cls.still_eps)),
            change_confirm=int(os.getenv("WATCH_CHANGE_CONFIRM", cls.change_confirm)),
            recalibrate_after=int(os.getenv("WATCH_RECALIBRATE_AFTER", cls.recalibrate_after)),
        )
