"""Table state database routes (contract of PoC/table-state-database, served under /api/v1)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.table_state.config import WatchConfig

TABLE = {"table_width_cm": 127, "table_length_cm": 254}


@pytest.fixture
def client():
    with TestClient(create_app(database_url="sqlite://", watch_config=WatchConfig(enabled=False))) as client:
        yield client


def ball(kind="FULL", w=10.0, l=20.0):
    return {"ball_type": kind, "location_width_cm": w, "location_length_cm": l}


def test_create_get_list_latest(client):
    first = client.post("/api/v1/states", json={**TABLE, "captured_at": "2026-01-01T10:00:00",
                                                "balls": [ball("WHITE"), ball("EIGHT", 50, 60)]})
    assert first.status_code == 201
    body = first.json()
    assert body["ball_count"] == 2 and {b["ball_type"] for b in body["balls"]} == {"WHITE", "EIGHT"}
    second = client.post("/api/v1/states", json={**TABLE, "captured_at": "2026-01-01T11:00:00", "balls": []}).json()

    by_id = lambda balls: sorted(balls, key=lambda b: b["ball_id"])  # noqa: E731  (stored order: ball_id)
    assert by_id(client.get(f"/api/v1/states/{body['state_id']}").json()["balls"]) == by_id(body["balls"])
    assert [s["state_id"] for s in client.get("/api/v1/states").json()] == [second["state_id"], body["state_id"]]
    assert client.get("/api/v1/states/latest").json()["state_id"] == second["state_id"]
    assert client.get("/api/v1/states", params={"limit": 1, "offset": 1}).json()[0]["state_id"] == body["state_id"]


def test_latest_and_unknown_return_404(client):
    assert client.get("/api/v1/states/latest").status_code == 404
    assert client.get("/api/v1/states/00000000-0000-0000-0000-000000000000").status_code == 404


@pytest.mark.parametrize("balls", [[ball("WHITE"), ball("WHITE")], [ball("EIGHT"), ball("EIGHT")],
                                   [ball(w=128)], [ball(l=255)], [ball(w=-1)]])
def test_invalid_balls_are_rejected(client, balls):
    assert client.post("/api/v1/states", json={**TABLE, "balls": balls}).status_code == 422


def test_replace_balls_and_delete(client):
    state = client.post("/api/v1/states", json={**TABLE, "balls": [ball()]}).json()
    url = f"/api/v1/states/{state['state_id']}"
    replaced = client.put(f"{url}/balls", json={"balls": [ball("HALF"), ball("UNKNOWN", 1, 1)]})
    assert replaced.status_code == 200 and replaced.json()["ball_count"] == 2
    assert client.put(f"{url}/balls", json={"balls": [ball(l=300)]}).status_code == 422
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_watcher_views_when_disabled(client):
    assert client.get("/api/v1/states/watcher").json()["phase"] == "disabled"
    assert client.get("/api/v1/table/live").status_code == 503
