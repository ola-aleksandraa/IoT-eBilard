"""Glue between the detection API (normalised 0-1 table coordinates) and the shot-planning engine (pixels)."""
from __future__ import annotations

from statistics import median
from typing import Iterable

from .geometry_builder import build_static_geometry
from .shot_scoring import get_top_shots, score_all_shots
from .table_types import TrackedBall
from .trajectory import find_all_shots

# The engine's constants (friction, margins, ...) are tuned in pixels for a table about this wide.
ENGINE_WIDTH = 1000.0


def plan_shots(balls: Iterable, table_ratio: float, top_n: int = 5,
               include_bank: bool = True, include_blocked: bool = False) -> dict:
    """balls: objects with id, kind, x, y, radius (x/y in 0-1 of table width/height, radius in 0-1 of height)."""
    balls = list(balls)
    W = ENGINE_WIDTH
    H = W / table_ratio
    engine_balls = [
        TrackedBall(track_id=b.id, class_name="cue_ball" if b.kind == "cue" else b.kind,
                    center_x=b.x * W, center_y=b.y * H, radius=b.radius * H)
        for b in balls
    ]
    cue = [b for b in engine_balls if b.class_name == "cue_ball"]
    if len(cue) != 1:
        return {"status": "no_cue_ball" if not cue else "multiple_cue_balls",
                "cue_ball_id": None, "shots": [], "blocked": []}
    if len(engine_balls) < 2:
        return {"status": "no_targets", "cue_ball_id": cue[0].track_id, "shots": [], "blocked": []}

    geometry = build_static_geometry([[0, 0], [W, 0], [W, H], [0, H]],
                                     ball_radius=median(b.radius for b in engine_balls))
    all_shots = find_all_shots(engine_balls, geometry)
    if not include_bank:
        all_shots = [s for s in all_shots if s.shot_type == "direct" or s.is_blocked]
    score_all_shots(all_shots, geometry, engine_balls)
    top = get_top_shots(shots=all_shots, top_n=top_n, table_layout=geometry, balls=engine_balls,
                        min_score=0.0, deduplicate=True)
    blocked = [s for s in all_shots if s.is_blocked] if include_blocked else []

    return {"status": "ok", "cue_ball_id": cue[0].track_id,
            "shots": [_serialise(s, engine_balls, W, H) for s in top],
            "blocked": [_serialise(s, engine_balls, W, H) for s in blocked[:20]]}


def _serialise(shot, engine_balls, W, H) -> dict:
    data = shot.to_dict()
    norm = lambda p: None if p is None else [p[0] / W, p[1] / H]  # noqa: E731
    for key in ("cue_path", "target_path", "cue_deflect_path"):
        data[key] = [norm(p) for p in data[key]]
    data["ghost_pos"] = norm(data["ghost_pos"])
    data["bank_point"] = norm(data["bank_point"])
    data["target_ball_id"] = engine_balls[data["target_ball"]].track_id
    return data
