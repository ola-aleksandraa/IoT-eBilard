"""Run the scripted game (scripts/fake_pi.py) through the real watcher and database, frame by frame.

    uv run --frozen python -m scripts.watch_scenario                    # temporary SQLite database
    uv run --frozen python -m scripts.watch_scenario --database-url mysql+pymysql://...

Prints the watcher phase after every frame and the stored states, read back through the
website's own /api/v1/states routes. Exits non-zero if the stored states differ from the
expected ones (A: 6 balls, B: 5 balls, C: 4 balls).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.table_state.config import WatchConfig
from app.table_state.database import Database
from app.table_state.pi_client import PiClient
from app.table_state.watcher import TableWatcher

from .fake_pi import EXPECTED_BALL_COUNTS, create_fake_pi, scenario


def run(database_url: str, verbose: bool = True) -> list[dict]:
    frames = scenario()
    config = WatchConfig(enabled=True)
    db = Database(database_url)
    db.create_schema()
    fake_pi = create_fake_pi(frames, loop=False)
    watcher = TableWatcher(config, db.session_factory, pi=PiClient(client=TestClient(fake_pi)))
    watcher.load_baseline()

    for n, note in enumerate(f.note for f in frames):
        before = watcher.states_stored
        watcher.step()
        stored = watcher.states_stored > before
        if verbose:
            status = watcher.status()
            mark = f"  -> STORED {status.last_state_id}" if stored else ""
            print(f"{n:3d} {note:<42} {status.phase:<12} window {status.window_filled}/{status.window_size}{mark}")
    db.dispose()

    with TestClient(create_app(database_url=database_url, watch_config=WatchConfig(enabled=False))) as api:
        summaries = api.get("/api/v1/states", params={"limit": 500}).json()
        return [api.get(f"/api/v1/states/{s['state_id']}").json() for s in reversed(summaries)]  # oldest first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", help="defaults to a fresh temporary SQLite file")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        url = args.database_url or f"sqlite:///{Path(tmp) / 'scenario.db'}"
        states = run(url)

    print("\nStored table states (oldest first):")
    for state in states:
        balls = ", ".join(f"{b['ball_type']}@({b['location_width_cm']:.1f},{b['location_length_cm']:.1f})"
                          for b in sorted(state["balls"], key=lambda b: b["location_length_cm"]))
        print(f"  {state['captured_at']}  {state['ball_count']} balls  {state['image_ref']}\n    {balls}")

    counts = [s["ball_count"] for s in states]
    if counts != EXPECTED_BALL_COUNTS:
        print(f"\nFAIL: expected ball counts {EXPECTED_BALL_COUNTS}, got {counts}")
        return 1
    print(f"\nOK: {len(states)} states stored with ball counts {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
