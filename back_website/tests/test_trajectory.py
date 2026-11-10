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
    r = client.post("/api/v1/shots", json={"balls": [ball(0, "cue", 0.5, 0.5), ball(1, "solid", 0.75, 0.25, 0.026)], "table_ratio": 1.0})
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
    body = client.post("/api/v1/shots", json={"balls": balls, "top_n": 20, "include_blocked": True}).json()
    # a straight line cue -> ball 1 passes through ball 2, so no unblocked shot may run along y = 0.5 to ball 1
    along_centre = [s for s in body["shots"] if s["target_ball_id"] == 1 and s["shot_type"] == "direct"
                    and abs(s["cue_path"][0][1] - 0.5) < 0.02 and abs(s["cue_path"][-1][1] - 0.5) < 0.02]
    assert not along_centre
    assert any(s["blocked_reason"] for s in body["blocked"])


@pytest.mark.parametrize("balls, status", [([], "no_cue_ball"), ([ball(1, "solid", 0.5, 0.5)], "no_cue_ball"),
                                           ([ball(0, "cue", 0.5, 0.5)], "no_targets"),
                                           ([ball(0, "cue", 0.2, 0.5), ball(1, "cue", 0.6, 0.5)], "multiple_cue_balls")])
def test_degenerate_scenes_are_not_errors(balls, status):
    r = client.post("/api/v1/shots", json={"balls": balls})
    assert r.status_code == 200 and r.json()["status"] == status and r.json()["shots"] == []


def test_validation_and_extra_detection_fields():
    assert client.post("/api/v1/shots", json={"balls": [ball(0, "cue", 1.5, 0.5)]}).status_code == 422
    assert client.post("/api/v1/shots", json={"balls": [], "table_ratio": 9}).status_code == 422
    full = {**ball(0, "cue", 0.2, 0.5), "source_x": 0.1, "color": "#fff", "confidence": 0.9}
    assert client.post("/api/v1/shots", json={"balls": [full, ball(1, "solid", 0.6, 0.4)]}).status_code == 200


def test_full_rack_is_fast_enough_for_live_use():
    balls = [ball(0, "cue", 0.2, 0.5)] + [ball(i, "solid", 0.55 + 0.04 * (i // 5), 0.3 + 0.1 * (i % 5)) for i in range(1, 11)]
    start = time.perf_counter()
    r = client.post("/api/v1/shots", json={"balls": balls})
    assert r.status_code == 200 and time.perf_counter() - start < 2.0


@pytest.mark.parametrize("path", ["shots", "shots/predict", "shots/simulate"])
def test_shot_routes_reject_duplicate_labels_and_nonfinite_coordinates(path):
    options = {"balls": [ball(1, "cue", .2, .5), ball(1, "solid", .6, .5)], "aim_x": .8, "aim_y": .5}
    if path == "shots":
        options.pop("aim_x")
        options.pop("aim_y")
    assert client.post("/api/v1/" + path, json=options).status_code == 422
    options["balls"][1]["id"] = 2
    options["balls"][1]["x"] = float("inf")
    import json
    response = client.post("/api/v1/" + path, content=json.dumps(options), headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_cue_aim_predicts_contact_and_simulates_time_sampled_motion():
    options = {"balls": [ball(1, "cue", .2, .5), ball(2, "solid", .6, .5)], "aim_x": .9, "aim_y": .5}
    predicted = client.post("/api/v1/shots/predict", json=options)
    assert predicted.status_code == 200
    assert predicted.json()["first_ball_id"] == 2
    response = client.post("/api/v1/shots/simulate", json={**options, "power": .6})
    assert response.status_code == 200
    motion = response.json()
    assert motion["status"] == "ok" and motion["first_ball_id"] == 2
    assert 0 < motion["duration"] <= 10 and motion["dt"] > 0
    assert {entry["id"] for entry in motion["balls"]} == {1, 2}
    assert any(event["type"] == "contact" for event in motion["events"])
    cue = next(entry for entry in motion["balls"] if entry["id"] == 1)
    assert cue["path"][0] == pytest.approx([.2, .5])
    assert cue["path"][-1][0] > .2
    from tests.test_api import assert_numerical
    assert_numerical(motion)


@pytest.mark.parametrize("path", ["predict", "simulate"])
def test_cue_aim_handles_missing_cue_and_invalid_aim(path):
    endpoint = "/api/v1/shots/" + path
    assert client.post(endpoint, json={"balls": [], "aim_x": .8, "aim_y": .5}).json()["status"] == "no_cue_ball"
    response = client.post(endpoint, json={"balls": [ball(1, "cue", .2, .5), ball(2, "solid", .6, .5)], "aim_x": .2, "aim_y": .5})
    assert response.status_code == 200 and response.json()["status"] == "invalid_aim"


def test_shot_routes_share_bounded_admission_control():
    slot = app.state.processing_slot
    slot.acquire()
    try:
        for path in ("shots", "shots/predict", "shots/simulate"):
            response = client.post("/api/v1/" + path, json={"balls": [], "aim_x": .8, "aim_y": .5} if path != "shots" else {"balls": []})
            assert response.status_code == 503 and response.headers["retry-after"] == "1"
    finally:
        slot.release()


def test_disabling_banks_also_excludes_blocked_bank_candidates():
    layout = [ball(1, "cue", .2, .5), ball(2, "solid", .8, .5), ball(3, "striped", .5, .5)]
    result = client.post("/api/v1/shots", json={"balls": layout, "include_bank": False, "include_blocked": True}).json()
    assert result["blocked"]
    assert all(s["shot_type"] == "direct" for s in result["shots"] + result["blocked"])


def test_zero_power_leaves_a_separated_layout_stationary():
    layout = [ball(1, "cue", .2, .5), ball(2, "solid", .6, .5)]
    result = client.post("/api/v1/shots/simulate", json={"balls": layout, "aim_x": .9, "aim_y": .5, "power": 0}).json()
    assert result["status"] == "ok" and not result["events"]
    for original, motion in zip(layout, result["balls"]):
        assert all(point == pytest.approx([original["x"], original["y"]]) for point in motion["path"])


def test_openapi_describes_all_numerical_shot_results():
    schema = client.get("/openapi.json").json()
    for path, name in [("shots", "ShotsResult"), ("shots/predict", "PredictionResult"), ("shots/simulate", "SimulationResult")]:
        response = schema["paths"]["/api/v1/" + path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert response["$ref"] == "#/components/schemas/" + name
