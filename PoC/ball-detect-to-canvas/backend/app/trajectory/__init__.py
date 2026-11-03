"""Shot planning (ghost-ball) engine."""
from .service import plan_shots, predict_shot, simulate_motion, POWER_PRESETS_MPS

__all__ = ["plan_shots", "predict_shot", "simulate_motion", "POWER_PRESETS_MPS"]
