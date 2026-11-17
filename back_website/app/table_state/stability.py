"""Change detection and sliding-window settling of detected ball layouts. Pure logic, no I/O.

The detector is stateless and its ball ids are frame-local, so balls are matched between
frames by position. Distances are measured in table-height units: dx = (x1 - x2) * table_ratio,
dy = y1 - y2 (x, y are normalized to cloth width/height, as returned by back_raspberry).

Phases
  initializing  no stored layout yet; the first window that agrees becomes the baseline
  stable        frames are compared with the stored baseline; `change_confirm` consecutive
                differing frames start settling (a single detector glitch does not)
  settling      the last `window` frames slide over the incoming sequence; once all of them
                agree, their median layout is emitted (if it differs from the baseline)
A frame without a visible table (hand, cue, player over the camera) restarts the window.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Kind = Literal["cue", "eight", "solid", "striped", "unknown"]
Phase = Literal["initializing", "stable", "settling"]
UNIQUE_KINDS = ("cue", "eight")
MAX_MATCH_DISTANCE = 0.35  # beyond this two detections are never considered the same ball
KIND_MISMATCH_PENALTY = 0.12  # prefer pairing a cue/eight with a ball of the same kind


@dataclass(frozen=True)
class TrackedBall:
    kind: Kind
    x: float
    y: float
    radius: float = 0.026


@dataclass(frozen=True)
class Frame:
    """One detector result. balls=None means the table was not visible ("searching")."""
    balls: tuple[TrackedBall, ...] | None
    acquired_at: datetime | None = None
    frame_id: str | None = None


@dataclass(frozen=True)
class SettledLayout:
    balls: tuple[TrackedBall, ...]
    acquired_at: datetime | None
    frame_id: str | None


@dataclass(frozen=True)
class StabilityConfig:
    window: int = 4            # frames that must agree before a layout is stored
    move_eps: float = 0.015    # ball displacement that counts as a change (~1.9 cm on a 127 cm table)
    still_eps: float = 0.006   # max spread inside a stable window (~0.8 cm)
    change_confirm: int = 2    # consecutive differing frames needed to leave "stable"
    table_ratio: float = 2.0

    def __post_init__(self):
        if self.window < 2:
            raise ValueError("window must be at least 2 frames")
        if not 0 < self.still_eps <= self.move_eps:
            raise ValueError("require 0 < still_eps <= move_eps")
        if self.change_confirm < 1:
            raise ValueError("change_confirm must be at least 1")
        if not 1 <= self.table_ratio <= 3:
            raise ValueError("table_ratio must be between 1 and 3")


def distance(a: TrackedBall, b: TrackedBall, table_ratio: float) -> float:
    return math.hypot((a.x - b.x) * table_ratio, a.y - b.y)


def match(a: tuple[TrackedBall, ...], b: tuple[TrackedBall, ...], table_ratio: float) -> list[tuple[int, int, float]]:
    """Greedy one-to-one nearest-neighbour pairing (at most 24 balls, so O(n² log n) is fine)."""
    pairs = []
    for i, ball_a in enumerate(a):
        for j, ball_b in enumerate(b):
            d = distance(ball_a, ball_b, table_ratio)
            if d > MAX_MATCH_DISTANCE:
                continue
            special = ball_a.kind in UNIQUE_KINDS or ball_b.kind in UNIQUE_KINDS
            penalty = KIND_MISMATCH_PENALTY if special and ball_a.kind != ball_b.kind else 0.0
            pairs.append((d + penalty, d, i, j))
    pairs.sort()
    used_a: set[int] = set()
    used_b: set[int] = set()
    result = []
    for _cost, d, i, j in pairs:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        result.append((i, j, d))
    return result


def layouts_agree(a: tuple[TrackedBall, ...], b: tuple[TrackedBall, ...], table_ratio: float, eps: float) -> bool:
    """Same number of balls and every ball paired with one at most `eps` away.

    Category flicker alone (e.g. solid <-> unknown) is not a change: the detector's categories
    are noisier than its positions. Categories are decided by majority vote in `aggregate`.
    """
    if len(a) != len(b):
        return False
    pairs = match(a, b, table_ratio)
    return len(pairs) == len(a) and all(d <= eps for _i, _j, d in pairs)


def _vote(kinds: list[Kind]) -> Kind:
    """Most frequent definite category; "unknown" only if it was seen strictly more often.

    Ties between definite categories go to the newest frame's (first in `kinds`) category.
    """
    counts = Counter(k for k in kinds if k != "unknown")
    if not counts:
        return "unknown"
    best = max(counts.values())
    winner = next(k for k in kinds if counts.get(k) == best)
    return winner if best >= kinds.count("unknown") else "unknown"


def aggregate(window: list[tuple[TrackedBall, ...]], table_ratio: float) -> tuple[TrackedBall, ...]:
    """Median position and majority category per ball, anchored on the newest frame."""
    reference = window[-1]
    samples: list[list[TrackedBall]] = [[ball] for ball in reference]  # newest sample first
    for frame in window[:-1]:
        for i, j, _d in match(reference, frame, table_ratio):
            samples[i].append(frame[j])
    balls = [TrackedBall(kind=_vote([s.kind for s in group]),
                         x=statistics.median(s.x for s in group),
                         y=statistics.median(s.y for s in group),
                         radius=statistics.median(s.radius for s in group))
             for group in samples]
    # The cue and the eight exist once; demote weaker duplicate claims to "unknown".
    for kind in UNIQUE_KINDS:
        claims = sorted((i for i, b in enumerate(balls) if b.kind == kind),
                        key=lambda i: -sum(s.kind == kind for s in samples[i]))
        for i in claims[1:]:
            balls[i] = TrackedBall("unknown", balls[i].x, balls[i].y, balls[i].radius)
    return tuple(sorted(balls, key=lambda b: (b.x, b.y)))


@dataclass
class TableStateTracker:
    config: StabilityConfig = field(default_factory=StabilityConfig)
    baseline: tuple[TrackedBall, ...] | None = None

    def __post_init__(self):
        self._window: deque[Frame] = deque(maxlen=self.config.window)
        self._change_streak: list[Frame] = []
        self.phase: Phase = "stable" if self.baseline is not None else "initializing"

    @property
    def window_filled(self) -> int:
        return len(self._window)

    def update(self, frame: Frame) -> SettledLayout | None:
        """Feed one frame; returns a layout when a new settled state should be stored."""
        cfg = self.config
        if frame.balls is None:  # table not visible: whatever was accumulating is no longer contiguous
            self._window.clear()
            self._change_streak.clear()
            return None

        if self.phase == "stable":
            if layouts_agree(frame.balls, self.baseline, cfg.table_ratio, cfg.move_eps):
                self._change_streak.clear()
                return None
            self._change_streak.append(frame)
            if len(self._change_streak) < cfg.change_confirm:
                return None
            self.phase = "settling"
            self._window.clear()
            self._window.extend(self._change_streak)
            self._change_streak.clear()
            return self._try_settle()

        self._window.append(frame)
        return self._try_settle()

    def _try_settle(self) -> SettledLayout | None:
        cfg = self.config
        if len(self._window) < cfg.window:
            return None
        frames = [f.balls for f in self._window]
        newest = frames[-1]
        if not all(layouts_agree(f, newest, cfg.table_ratio, cfg.still_eps) for f in frames[:-1]):
            return None  # still moving: keep sliding
        settled = aggregate(frames, cfg.table_ratio)
        last = self._window[-1]
        previous, self.baseline = self.baseline, settled
        self.phase = "stable"
        self._window.clear()
        if previous is not None and layouts_agree(settled, previous, cfg.table_ratio, cfg.move_eps):
            return None  # e.g. a ball lifted and put back: nothing new to store
        return SettledLayout(settled, last.acquired_at, last.frame_id)
