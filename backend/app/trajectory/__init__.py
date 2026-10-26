"""Shot planning (ghost-ball) engine."""
from __future__ import annotations

from .service import plan_shots, predict_shot, simulate_motion

__all__ = ["plan_shots", "predict_shot", "simulate_motion"]
