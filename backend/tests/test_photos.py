"""Real-photo regressions, with approximate hand-labelled visible centers.

The minimum match counts document current recall; they are not perfect-accuracy
claims. Class labels are deliberately limited to unambiguous cue candidates.
"""

import json
import math
import os
from pathlib import Path

import pytest

from tests.test_api import application, client, upload, assert_numerical

ANNOTATIONS = json.loads((Path(__file__).parent / "fixtures" / "photos" / "annotations.json").read_text())
PHOTOS = Path(os.environ.get("EBILARD_PHOTO_DIR", Path(__file__).parent.parent / "evaluation-output" / "photos"))
pytestmark = pytest.mark.skipif(
    not all((PHOTOS / name).is_file() for name in ANNOTATIONS),
    reason="Optional photo inputs are local. Set EBILARD_PHOTO_DIR to a directory containing table-1.png through table-3.png.",
)


@pytest.mark.parametrize("name", ANNOTATIONS)
def test_photo_detections_are_visible_balls_without_rail_or_pocket_phantoms(client, name):
    response = upload(client, (PHOTOS / name).read_bytes())
    assert response.status_code == 200
    body = response.json()
    assert_numerical(body)
    assert body["table_status"] == "detected"
    width, height = body["source"]["width"], body["source"]["height"]
    balls = body["detection"]["balls"]
    remaining = ANNOTATIONS[name]["centers"].copy()
    for ball in balls:
        center = (ball["source_x"] * (width - 1), ball["source_y"] * (height - 1))
        nearest = min(remaining, key=lambda p: math.dist(center, p))
        # 25 px is an association tolerance on these 1920x1080 frames, not an
        # asserted measurement accuracy. It still rejects cushion/pocket ghosts.
        assert math.dist(center, nearest) < 25, (name, center)
        remaining.remove(nearest)
    assert len(balls) >= ANNOTATIONS[name]["minimum_matches"]
    cue = next(ball for ball in balls if ball["kind"] == "cue")
    assert math.dist((cue["source_x"] * (width - 1), cue["source_y"] * (height - 1)),
                     ANNOTATIONS[name]["cue"]) < 12


def test_real_photo_layout_drives_every_shot_endpoint(client):
    result = upload(client, (PHOTOS / "table-3.png").read_bytes()).json()["detection"]
    layout = {"balls": result["balls"], "table_ratio": result["geometry"]["table_ratio"]}
    for path in ("shots", "shots/predict", "shots/simulate"):
        options = layout if path == "shots" else {**layout, "aim_x": .9, "aim_y": .5}
        response = client.post("/api/v1/" + path, json=options)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ok"
        assert_numerical(response.json())
