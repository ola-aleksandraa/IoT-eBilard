import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trajectory.geometry_builder import build_static_geometry

client = TestClient(app)


def ball(id, kind, x, y, r=0.026):
    return {"id": id, "kind": kind, "x": x, "y": y, "radius": r}


def test_geometry_has_six_pockets_and_inward_normals():
    g = build_static_geometry([[0, 0], [1000, 0], [1000, 500], [0, 500]])
    assert len(g.pockets) == 6 and len(g.pocket_gates) == 6 and len(g.solid_cushions) == 6
    assert g.pockets[0].tolist() == [0, 0] and g.pockets[5].tolist() == [1000, 500]
    names = dict(g.cushion_normals)
    assert names["top"][1] > 0 and names["bottom"][1] < 0 and names["left"][0] > 0 and names["right"][0] < 0


def test_straight_shot_into_corner_pocket():
    # cue, object ball and top-right corner pocket lie on one diagonal -> a straight, uncut shot
    r = client.post("/api/shots", json={"balls": [ball(0, "cue", 0.5, 0.5), ball(1, "solid", 0.75, 0.25, 0.026)], "table_ratio": 1.0})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["cue_ball_id"] == 0
    straight = [s for s in body["shots"] if s["shot_type"] == "direct" and s["pocket"] == 2]
    assert straight, body["shots"]
    shot = straight[0]
    assert shot["target_ball_id"] == 1 and not shot["is_blocked"]
    assert abs(shot["cut_angle"]) < 1.0
    ghost = shot["ghost_pos"]
    assert ghost[0] < 0.75 and ghost[1] > 0.25  # ghost ball sits behind the object ball, away from the pocket
    for path in (shot["cue_path"], shot["target_path"]):
        assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in path)


def test_blocking_ball_removes_the_straight_line_shot():
    balls = [ball(0, "cue", 0.2, 0.5), ball(1, "solid", 0.8, 0.5), ball(2, "striped", 0.5, 0.5)]
    body = client.post("/api/shots", json={"balls": balls, "top_n": 20, "include_blocked": True}).json()
    # a straight line cue -> ball 1 passes through ball 2, so no unblocked shot may run along y = 0.5 to ball 1
    along_centre = [s for s in body["shots"] if s["target_ball_id"] == 1 and s["shot_type"] == "direct"
                    and abs(s["cue_path"][0][1] - 0.5) < 0.02 and abs(s["cue_path"][-1][1] - 0.5) < 0.02]
    assert not along_centre
    assert any(s["blocked_reason"] for s in body["blocked"])


@pytest.mark.parametrize("balls, status", [([], "no_cue_ball"), ([ball(1, "solid", 0.5, 0.5)], "no_cue_ball"),
                                           ([ball(0, "cue", 0.5, 0.5)], "no_targets"),
                                           ([ball(0, "cue", 0.2, 0.5), ball(1, "cue", 0.6, 0.5)], "multiple_cue_balls")])
def test_degenerate_scenes_are_not_errors(balls, status):
    r = client.post("/api/shots", json={"balls": balls})
    assert r.status_code == 200 and r.json()["status"] == status and r.json()["shots"] == []


def test_validation_and_extra_detection_fields():
    assert client.post("/api/shots", json={"balls": [ball(0, "cue", 1.5, 0.5)]}).status_code == 422
    assert client.post("/api/shots", json={"balls": [], "table_ratio": 9}).status_code == 422
    full = {**ball(0, "cue", 0.2, 0.5), "source_x": 0.1, "color": "#fff", "confidence": 0.9}
    assert client.post("/api/shots", json={"balls": [full, ball(1, "solid", 0.6, 0.4)]}).status_code == 200


def test_full_rack_is_fast_enough_for_live_use():
    balls = [ball(0, "cue", 0.2, 0.5)] + [ball(i, "solid", 0.55 + 0.04 * (i // 5), 0.3 + 0.1 * (i % 5)) for i in range(1, 11)]
    start = time.perf_counter()
    r = client.post("/api/shots", json={"balls": balls})
    assert r.status_code == 200 and time.perf_counter() - start < 2.0
