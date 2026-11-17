"""Change detection and sliding-window settling (pure logic)."""

import random

import pytest

from app.table_state.stability import (Frame, StabilityConfig, TableStateTracker, TrackedBall, aggregate,
                                       layouts_agree, match)

CFG = StabilityConfig(window=4, move_eps=0.015, still_eps=0.006, change_confirm=2, table_ratio=2.0)
A = (TrackedBall("cue", 0.25, 0.5), TrackedBall("solid", 0.75, 0.45), TrackedBall("striped", 0.8, 0.6))
B = (TrackedBall("cue", 0.55, 0.3), TrackedBall("solid", 0.75, 0.45), TrackedBall("striped", 0.8, 0.6))


def noisy(layout, rng, jitter=0.0015, shuffle=True):
    balls = [TrackedBall(b.kind, b.x + rng.uniform(-jitter, jitter), b.y + rng.uniform(-jitter, jitter), b.radius)
             for b in layout]
    if shuffle:  # detector ids/order are frame-local
        rng.shuffle(balls)
    return Frame(tuple(balls))


def feed(tracker, frames):
    return [tracker.update(f) for f in frames]


@pytest.fixture
def rng():
    return random.Random(1)


def test_distance_uses_table_height_units():
    a, b = TrackedBall("solid", 0.10, 0.5), TrackedBall("solid", 0.11, 0.5)
    (_, _, d), = match((a,), (b,), table_ratio=2.0)
    assert d == pytest.approx(0.02)


def test_matching_is_order_independent_and_prefers_same_special_kind():
    cue, eight = TrackedBall("cue", 0.5, 0.5), TrackedBall("eight", 0.5, 0.52)
    pairs = match((cue, eight), (TrackedBall("eight", 0.5, 0.505), TrackedBall("cue", 0.5, 0.515)), 2.0)
    assert sorted((i, j) for i, j, _ in pairs) == [(0, 1), (1, 0)]


def test_layouts_agree_ignores_category_flicker_but_not_count_or_motion():
    flicker = tuple(TrackedBall("unknown" if b.kind == "solid" else b.kind, b.x, b.y) for b in A)
    assert layouts_agree(A, flicker, 2.0, 0.006)
    assert not layouts_agree(A, A[:2], 2.0, 0.006)
    assert not layouts_agree(A, B, 2.0, 0.015)


def test_aggregate_takes_median_position_and_majority_kind():
    window = [(TrackedBall("solid", x, 0.5),) for x in (0.500, 0.502, 0.500, 0.501)]
    window[1] = (TrackedBall("unknown", 0.502, 0.5),)
    (ball,) = aggregate(window, 2.0)
    assert ball.kind == "solid"
    assert ball.x == pytest.approx(0.5005)


def test_aggregate_never_returns_two_cue_balls():
    window = [(TrackedBall("cue", 0.2, 0.5), TrackedBall("cue", 0.8, 0.5))] * 3
    kinds = sorted(b.kind for b in aggregate(window, 2.0))
    assert kinds == ["cue", "unknown"]


def test_first_stable_window_initializes_the_baseline(rng):
    tracker = TableStateTracker(CFG)
    results = feed(tracker, [noisy(A, rng) for _ in range(4)])
    assert results[:3] == [None] * 3 and results[3] is not None
    assert len(results[3].balls) == 3 and tracker.phase == "stable"


def test_jitter_below_threshold_never_triggers_a_store(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    assert feed(tracker, [noisy(A, rng, jitter=0.004) for _ in range(50)]) == [None] * 50
    assert tracker.phase == "stable"


def test_single_glitch_frame_does_not_start_settling(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    feed(tracker, [Frame(A[1:]), noisy(A, rng)])  # cue occluded once
    assert tracker.phase == "stable"


def test_moved_ball_is_stored_only_after_the_window_stops_changing(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    rolling = [Frame((TrackedBall("cue", 0.25 + 0.06 * k, 0.5 - 0.04 * k),) + A[1:]) for k in range(1, 5)]
    assert feed(tracker, rolling) == [None] * 4
    assert tracker.phase == "settling"
    settled = feed(tracker, [noisy(B, rng) for _ in range(4)])
    assert settled[:3] == [None] * 3
    stored = settled[3]
    assert stored is not None
    assert layouts_agree(stored.balls, B, 2.0, 0.003)


def test_pocketed_ball_is_a_change(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    results = feed(tracker, [Frame(A[:2])] * 4)
    assert results[-1] is not None and len(results[-1].balls) == 2


def test_lost_table_restarts_the_window(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    feed(tracker, [Frame(B)] * 3)
    assert tracker.window_filled == 3
    tracker.update(Frame(None))
    assert tracker.window_filled == 0
    assert feed(tracker, [Frame(B)] * 3) == [None] * 3
    assert tracker.update(Frame(B)) is not None


def test_change_that_returns_to_the_baseline_is_not_stored(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    lifted = Frame((TrackedBall("cue", 0.30, 0.5),) + A[1:])
    results = feed(tracker, [lifted, lifted] + [noisy(A, rng) for _ in range(6)])
    assert results == [None] * 8
    assert tracker.phase == "stable"


def test_settled_layout_carries_the_newest_frame_reference(rng):
    tracker = TableStateTracker(CFG, baseline=A)
    frames = [Frame(B, frame_id=f"f{k}") for k in range(4)]
    assert feed(tracker, frames)[-1].frame_id == "f3"


@pytest.mark.parametrize("kwargs", [{"window": 1}, {"still_eps": 0.02}, {"change_confirm": 0}, {"table_ratio": 4}])
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        StabilityConfig(**kwargs)
