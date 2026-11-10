"""Real-photo regressions, with approximate hand-labelled visible centers.

The minimum match counts document current recall; they are not perfect-accuracy
claims. Class labels are deliberately limited to unambiguous cue candidates.
"""

import json
import math
import os
from pathlib import Path

import pytest
import numpy as np
from app.engine.lens import distort_points, undistort_points
from app.engine.models import Calibration
from app.services.auto_lens import line_error

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
    calibration = Calibration.model_validate(body["calibration"])
    def original_center(ball):
        return distort_points([[ball["source_x"] * (width - 1), ball["source_y"] * (height - 1)]], calibration.lens)[0]
    remaining = ANNOTATIONS[name]["centers"].copy()
    for ball in balls:
        center = original_center(ball)
        nearest = min(remaining, key=lambda p: math.dist(center, p))
        # 25 px is an association tolerance on these 1920x1080 frames, not an
        # asserted measurement accuracy. It still rejects cushion/pocket ghosts.
        assert math.dist(center, nearest) < 25, (name, center)
        remaining.remove(nearest)
    assert len(balls) >= ANNOTATIONS[name]["minimum_matches"]
    cue = next(ball for ball in balls if ball["kind"] == "cue")
    assert math.dist(original_center(cue),
                     ANNOTATIONS[name]["cue"]) < 12


def test_real_photo_layout_is_numerical(client):
    response = upload(client, (PHOTOS / "table-3.png").read_bytes())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detection"]["balls"]
    assert_numerical(body)


@pytest.mark.parametrize('number,rows', [
    (2, [[[344, 334], [826, 292], [1315, 280]], [[195, 758], [850, 753], [1520, 668]]]),
    (3, [[[344, 308], [831, 272], [1316, 267]], [[193, 731], [851, 735], [1524, 654]]]),
])
def test_photo_correction_improves_independently_labelled_pocket_rows(client, number, rows):
    # Approximate visible pocket centers, independent of the rail pixels used
    # for fitting. Corner and side pocket mouths have different shapes, so this
    # tests improvement, not exact collinearity or physical calibration accuracy.
    body = upload(client, (PHOTOS / f'table-{number}.png').read_bytes()).json()
    lens = Calibration.model_validate(body['calibration']).lens
    assert lens is not None
    for row in rows:
        assert line_error(undistort_points(row, lens)) < line_error(np.array(row)) * .65


def test_occlusion_does_not_invent_a_lens_but_locked_correction_is_reused(client):
    occluded = (PHOTOS / 'table-1.png').read_bytes()
    assert upload(client, occluded).json()['calibration']['lens'] is None
    calibration = upload(client, (PHOTOS / 'table-2.png').read_bytes()).json()['calibration']
    body = upload(client, occluded, {'calibration': calibration}).json()
    assert body['calibration'] == calibration
    assert body['source']['lens_corrected'] is True
    assert body['detection']['counts']['total'] >= ANNOTATIONS['table-1.png']['minimum_matches']
