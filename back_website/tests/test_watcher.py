"""Watcher + database integration, driven by the scripted fake Pi (scripts/fake_pi.py)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.table_state.config import WatchConfig
from app.table_state.database import Database
from app.table_state.pi_client import PiClient
from app.table_state.stability import SettledLayout, TrackedBall
from app.table_state.repository import store_layout
from app.table_state.watcher import TableWatcher
from scripts.fake_pi import EXPECTED_BALL_COUNTS, LAYOUT_A, ScriptedFrame, create_fake_pi, scenario
from scripts.watch_scenario import run

CONFIG = WatchConfig(enabled=True)


@pytest.fixture
def db():
    database = Database("sqlite://")
    database.create_schema()
    yield database
    database.dispose()


def watcher_for(db, frames, config=CONFIG):
    pi = PiClient(client=TestClient(create_fake_pi(frames, loop=False)))
    watcher = TableWatcher(config, db.session_factory, pi=pi)
    watcher.load_baseline()
    return watcher


def test_full_game_scenario_stores_one_state_per_settled_shot(tmp_path):
    states = run(f"sqlite:///{tmp_path / 'scenario.db'}", verbose=False)
    assert [s["ball_count"] for s in states] == EXPECTED_BALL_COUNTS
    a, b, c = states
    assert sorted(x["ball_type"] for x in a["balls"]) == ["EIGHT", "FULL", "FULL", "HALF", "HALF", "WHITE"]
    assert "HALF" in {x["ball_type"] for x in b["balls"]} and "EIGHT" not in {x["ball_type"] for x in c["balls"]}
    # Normalized (x along, y across) -> cm (length along, width across); A's cue is at x=0.25, y=0.5.
    cue = next(x for x in a["balls"] if x["ball_type"] == "WHITE")
    assert cue["location_length_cm"] == pytest.approx(63.5, abs=0.5)
    assert cue["location_width_cm"] == pytest.approx(63.5, abs=0.5)
    assert all(s["image_ref"].startswith("pi-frame:") for s in states)
    assert a["captured_at"] < b["captured_at"] < c["captured_at"]


def test_restart_resumes_from_stored_baseline_without_duplicates(db):
    first = watcher_for(db, [ScriptedFrame("A", LAYOUT_A)] * 6)
    for _ in range(6):
        first.step()
    assert first.states_stored == 1
    second = watcher_for(db, [ScriptedFrame("A", LAYOUT_A)] * 6)
    assert second.tracker.phase == "stable"
    for _ in range(6):
        second.step()
    assert second.states_stored == 0


def test_live_frame_and_status_are_exposed(db):
    watcher = watcher_for(db, scenario())
    for _ in range(4):
        watcher.step()
    assert watcher.live.table_status == "detected" and len(watcher.live.balls) == 6
    status = watcher.status()
    assert status.phase == "stable" and status.states_stored == 1 and status.calibrated


class ScriptedTransport(httpx.BaseTransport):
    """Pi that answers with a fixed sequence of status codes for detect."""

    def __init__(self, codes):
        self.codes = list(codes)
        self.calibrations = 0

    def handle_request(self, request):
        if request.url.path.endswith("/calibrate"):
            self.calibrations += 1
            return httpx.Response(200, json={"table_status": "detected", "calibration": {"image_width": 1}})
        code = self.codes.pop(0)
        return httpx.Response(code, json={"detail": "scripted"})


def test_busy_pi_is_retried_and_errors_force_recalibration(db):
    transport = ScriptedTransport([503, 503, 500, 500, 500])
    config = WatchConfig(enabled=True, recalibrate_after=3)
    watcher = TableWatcher(config, db.session_factory,
                           pi=PiClient(client=httpx.Client(base_url="http://pi", transport=transport)))
    watcher.step(), watcher.step()
    assert watcher.last_error is None and transport.calibrations == 1  # busy is not a failure
    for _ in range(3):
        watcher.step()
    assert "500" in watcher.last_error
    assert watcher.status().calibrated is False  # dropped after 3 failures, recalibrates next step


def test_unreachable_pi_is_reported_not_raised(db):
    watcher = TableWatcher(WatchConfig(enabled=True, pi_url="http://127.0.0.1:9", pi_timeout_s=0.5), db.session_factory)
    watcher.step()
    assert "unreachable" in watcher.last_error


def test_store_layout_clamps_to_table_and_maps_kinds(db):
    layout = SettledLayout((TrackedBall("cue", 1.0, 1.0), TrackedBall("eight", 0.0, 0.0),
                            TrackedBall("striped", 0.5, 0.25), TrackedBall("unknown", 0.1, 0.1)), None, None)
    store_layout(db.session_factory, layout, 127, 254)
    with TestClient(create_app(database_url="sqlite://", watch_config=WatchConfig(enabled=False))) as api:
        assert api.get("/api/v1/states").json() == []  # separate in-memory database: sanity check of isolation
    from app.table_state.models import TableState
    with db.session_factory() as session:
        state = session.query(TableState).one()
        got = sorted((b.ball_type.value, b.location_width_cm, b.location_length_cm) for b in state.balls)
    assert got == [("EIGHT", 0, 0), ("HALF", 31.75, 127), ("UNKNOWN", 12.7, 25.4), ("WHITE", 127, 254)]


def test_app_lifespan_runs_the_watcher_thread(tmp_path):
    fake = TestClient(create_fake_pi(scenario(), loop=False))
    config = WatchConfig(enabled=True, interval_ms=50)
    app = create_app(database_url=f"sqlite:///{tmp_path / 'live.db'}", watch_config=config, pi_client=PiClient(client=fake))
    with TestClient(app) as api:
        import time
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and api.get("/api/v1/states/watcher").json()["states_stored"] < 3:
            time.sleep(0.05)
        assert api.get("/api/v1/states/watcher").json()["running"] is True
        assert [s["ball_count"] for s in api.get("/api/v1/states").json()] == EXPECTED_BALL_COUNTS[::-1]
        live = api.get("/api/v1/table/live").json()
        assert live["table_status"] == "detected" and live["table_ratio"] == 2
