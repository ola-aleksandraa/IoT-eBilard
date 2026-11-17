"""Scripted stand-in for the Raspberry Pi camera service (back_raspberry/), for watcher scenarios.

Serves the same JSON contract as back_raspberry for POST /api/v1/camera/calibrate and
POST /api/v1/camera/detect, but every detect call returns the next frame of a scripted game:

    uv run --frozen python -m scripts.fake_pi --port 8002            # loop the scenario
    uv run --frozen python -m scripts.fake_pi --port 8002 --once     # stop on the last layout

Then start the website backend with TABLE_WATCH_ENABLED=1 and watch /api/v1/states fill up.
"""

from __future__ import annotations

import argparse
import itertools
import random
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import FastAPI

RADIUS = 0.026
# Ball layouts in normalized cloth coordinates (x along the long side, y across), table ratio 2.
LAYOUT_A = {  # opening: cue on the head spot, a small rack
    "cue": ("cue", 0.25, 0.50), "eight": ("eight", 0.75, 0.50),
    "s1": ("solid", 0.78, 0.44), "s2": ("solid", 0.78, 0.56),
    "h1": ("striped", 0.81, 0.40), "h2": ("striped", 0.81, 0.60),
}
LAYOUT_B = {  # after shot 1: cue moved, s1 knocked away, h1 pocketed
    "cue": ("cue", 0.62, 0.38), "eight": ("eight", 0.75, 0.50),
    "s1": ("solid", 0.92, 0.25), "s2": ("solid", 0.78, 0.56),
    "h2": ("striped", 0.81, 0.60),
}
LAYOUT_C = {  # after shot 2: eight pocketed, cue drawn back
    "cue": ("cue", 0.30, 0.72),
    "s1": ("solid", 0.92, 0.25), "s2": ("solid", 0.78, 0.56),
    "h2": ("striped", 0.81, 0.60),
}


@dataclass(frozen=True)
class ScriptedFrame:
    note: str
    balls: dict[str, tuple[str, float, float]] | None  # None = table not visible
    jitter: float = 0.0015  # detector noise, normalized units (~0.2 cm)
    flicker: dict[str, str] = field(default_factory=dict)  # name -> wrongly reported kind


def _moving(a: dict, b: dict, steps: int, note: str) -> list[ScriptedFrame]:
    """Balls rolling from layout a to b; balls missing in b drop into a pocket halfway."""
    frames = []
    for k in range(1, steps + 1):
        t = k / (steps + 1)
        balls = {}
        for name, (kind, x, y) in a.items():
            if name in b:
                _, bx, by = b[name]
                balls[name] = (kind, x + (bx - x) * t, y + (by - y) * t)
            elif t < 0.5:
                balls[name] = (kind, x + (0.98 - x) * t, y + (0.02 - y) * t)  # heading to a corner pocket
        frames.append(ScriptedFrame(f"{note} (rolling {k}/{steps})", balls))
    return frames


def scenario() -> list[ScriptedFrame]:
    """A game in frames. Expected stored states: A (6 balls), B (5 balls), C (4 balls)."""
    without_cue = {k: v for k, v in LAYOUT_A.items() if k != "cue"}
    s2_lifted = dict(LAYOUT_B, s2=("solid", 0.83, 0.56))
    return [
        *[ScriptedFrame("opening layout A", LAYOUT_A)] * 5,
        ScriptedFrame("player leans over the camera", None),
        ScriptedFrame("cue ball hidden by a hand for one frame", without_cue),
        *[ScriptedFrame("layout A again", LAYOUT_A)] * 3,
        *_moving(LAYOUT_A, LAYOUT_B, 4, "shot 1"),
        ScriptedFrame("shot 1 settling, s1 misclassified", LAYOUT_B, flicker={"s1": "unknown"}),
        *[ScriptedFrame("layout B", LAYOUT_B)] * 5,
        *[ScriptedFrame("s2 lifted by a player", s2_lifted)] * 2,
        *[ScriptedFrame("s2 put back: layout B", LAYOUT_B)] * 5,
        *_moving(LAYOUT_B, LAYOUT_C, 3, "shot 2"),
        *[ScriptedFrame("layout C", LAYOUT_C)] * 6,
    ]


EXPECTED_BALL_COUNTS = [6, 5, 4]


def analysis_result(frame: ScriptedFrame, rng: random.Random, table_ratio: float = 2.0) -> dict:
    """A back_raspberry AnalysisResult with only the fields the website watcher reads, plus counts."""
    now = datetime.now(timezone.utc).isoformat()
    base = {"schema_version": "1.0", "frame_id": uuid.uuid4().hex, "client_frame_id": None,
            "source": {"kind": "camera", "width": 1920, "height": 1080, "acquired_at": now, "lens_corrected": False},
            "analysis_ms": 1.0}
    if frame.balls is None:
        return {**base, "table_status": "searching", "calibration": None, "detection": None}
    balls = []
    for i, (name, (kind, x, y)) in enumerate(sorted(frame.balls.items(), key=lambda kv: rng.random()), start=1):
        clip = lambda v: min(max(v + rng.uniform(-frame.jitter, frame.jitter), 0.0), 1.0)  # noqa: E731
        balls.append({"id": i, "kind": frame.flicker.get(name, kind), "x": clip(x), "y": clip(y), "radius": RADIUS,
                      "source_x": x, "source_y": y, "confidence": 0.9, "reason": "scripted",
                      "white_fraction": 0.0, "method": "scripted"})
    counts = {k: sum(b["kind"] == k for b in balls) for k in ("cue", "eight", "solid", "striped", "unknown")}
    return {**base, "table_status": "detected", "calibration": CALIBRATION,
            "detection": {"balls": balls, "counts": {"total": len(balls), **counts},
                          "geometry": {"table_ratio": table_ratio}, "cloth_hue": 60, "processing_ms": 1.0,
                          "warnings": []}}


CALIBRATION = {"image_width": 1920, "image_height": 1080,
               "corners": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}]}


def create_fake_pi(frames: list[ScriptedFrame] | None = None, loop: bool = True, seed: int = 7) -> FastAPI:
    frames = frames or scenario()
    source = itertools.cycle(frames) if loop else itertools.chain(frames, itertools.repeat(frames[-1]))
    rng = random.Random(seed)
    lock = threading.Lock()
    app = FastAPI(title="Fake Raspberry Pi camera (scripted scenario)")
    app.state.served = []  # notes of served frames, for logs/tests

    @app.get("/health")
    def health():
        return {"status": "ok", "engine": "OpenCV", "opencv_version": "fake", "version": "1.0.0"}

    @app.post("/api/v1/camera/calibrate")
    def calibrate(_body: dict | None = None):
        return {"source": {"kind": "camera", "width": 1920, "height": 1080,
                           "acquired_at": datetime.now(timezone.utc).isoformat(), "lens_corrected": False},
                "table_status": "detected", "calibration": CALIBRATION, "geometry": None}

    @app.post("/api/v1/camera/detect")
    def detect(body: dict | None = None):
        ratio = ((body or {}).get("settings") or {}).get("table_ratio", 2.0)
        with lock:
            frame = next(source)
            app.state.served.append(frame.note)
            return analysis_result(frame, rng, ratio)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--once", action="store_true", help="hold the final layout instead of looping")
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_fake_pi(loop=not args.once), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
