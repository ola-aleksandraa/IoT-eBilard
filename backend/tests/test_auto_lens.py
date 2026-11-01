"""Geometry regressions with known distortion, not merely self-reprojection."""

import cv2
import numpy as np
import pytest
from datetime import datetime, timezone

from app.engine.lens import distort_points, undistort_points
from app.engine.models import Calibration, LensCalibration, Settings
from app.services.auto_lens import estimate_table_lens, fit_lens, line_error
from tests.fixtures.synthetic import make_demo
from tests.test_api import application, client, upload


def lens_for(width, height, k):
    return LensCalibration(image_width=width, image_height=height,
        camera_matrix=[[float(width), 0, (width - 1) / 2], [0, float(width), (height - 1) / 2], [0, 0, 1]],
        distortion=[k, 0, 0, 0, 0])


@pytest.fixture(scope="module")
def barrel_frame():
    ideal, _ = make_demo()
    height, width = ideal.shape[:2]
    lens = lens_for(width, height, -.4)
    y, x = np.indices((height, width), dtype=np.float32)
    grid = undistort_points(np.stack([x, y], axis=-1).reshape(-1, 2), lens).reshape(height, width, 2).astype(np.float32)
    raw = cv2.remap(ideal, grid[:, :, 0], grid[:, :, 1], cv2.INTER_LINEAR)
    return raw, lens


@pytest.mark.parametrize("k", [-.6, -.3, .3])
def test_fit_recovers_known_distortion_and_straightens_six_pocket_rows(k):
    lens = lens_for(1200, 760, k)
    corners = np.array([[250., 180], [930, 140], [1030, 600], [130, 620]])
    rails = [a + np.linspace(.1, .9, 50)[:, None] * (b - a) for a, b in zip(corners, np.roll(corners, -1, axis=0))]
    distorted = [distort_points(rail, lens) for rail in rails]
    fitted = fit_lens(distorted, 1200, 760)
    assert fitted is not None
    assert fitted.distortion[0] == pytest.approx(k, abs=.01)
    for rail in distorted:
        assert line_error(undistort_points(rail, fitted)) < .1
    for a, b in [(corners[0], corners[1]), (corners[3], corners[2])]:
        pockets = np.array([a, (a + b) / 2, b])
        assert line_error(undistort_points(distort_points(pockets, lens), fitted)) < .1


def test_straight_perspective_and_single_bowed_edge_do_not_trigger_correction():
    corners = np.array([[220., 160], [990, 120], [1100, 620], [100, 640]])
    rails = [a + np.linspace(.1, .9, 50)[:, None] * (b - a) for a, b in zip(corners, np.roll(corners, -1, axis=0))]
    assert fit_lens(rails, 1200, 760) is None
    rails[0] = distort_points(rails[0], lens_for(1200, 760, -.4))
    assert fit_lens(rails, 1200, 760) is None
    assert estimate_table_lens(make_demo()[0], Settings()) is None
    assert estimate_table_lens(np.full((600, 800, 3), 150, np.uint8), Settings()) is None


def test_auto_calibration_reuses_correction_on_later_original_frames(client, barrel_frame, monkeypatch):
    raw, expected = barrel_frame
    data = cv2.imencode('.png', raw)[1].tobytes()
    result = upload(client, data).json()
    assert result['table_status'] == 'detected'
    calibration = result['calibration']
    assert calibration['lens']['distortion'][0] == pytest.approx(expected.distortion[0], abs=.025)
    assert result['source']['lens_corrected']
    assert result['detection']['geometry']['source_space'] == 'undistorted_oriented_pixels'
    assert len(result['detection']['balls']) >= 10
    def no_refit(*args):
        pytest.fail('A fixed calibration must bypass both table and lens fitting')
    monkeypatch.setattr('app.services.analysis.estimate_table_lens', no_refit)
    monkeypatch.setattr('app.services.analysis.find_calibration', no_refit)
    # A new frame contains a new ball at a known ideal source location.
    ideal_center = np.array([[650., 410.]])
    center = distort_points(ideal_center, expected)[0]
    frame = raw.copy()
    cv2.circle(frame, tuple(np.rint(center).astype(int)), 14, (25, 30, 220), -1)
    later = upload(client, cv2.imencode('.png', frame)[1].tobytes(), {'calibration': calibration}).json()
    assert later['calibration'] == calibration
    centers = np.array([[b['source_x'] * 1199, b['source_y'] * 759] for b in later['detection']['balls']])
    assert np.linalg.norm(centers - ideal_center, axis=1).min() < 7
    forward = np.array(later['detection']['geometry']['source_to_table'])
    for ball in later['detection']['balls']:
        mapped = forward @ [ball['source_x'] * 1199, ball['source_y'] * 759, 1]
        assert mapped[:2] / mapped[2] == pytest.approx([ball['x'], ball['y']], abs=1e-4)


def test_calibrate_endpoint_returns_same_reusable_lens_and_validates_options(client, barrel_frame):
    raw, _ = barrel_frame
    data = cv2.imencode('.png', raw)[1].tobytes()
    result = upload(client, data, endpoint='/api/v1/images/calibrate').json()
    calibration = result['calibration']
    assert calibration['lens'] is not None
    assert upload(client, data, {'calibration': calibration, 'lens': calibration['lens']}).status_code == 422
    bad = {**calibration['lens'], 'image_width': 640}
    with pytest.raises(ValueError, match='resolution'):
        Calibration.model_validate({**calibration, 'lens': bad})
    assert upload(client, cv2.imencode('.png', raw[::2, ::2])[1].tobytes(), {'calibration': calibration}).status_code == 422
    # Explicit camera intrinsics are authoritative and never fitted again.
    explicit = upload(client, data, {'lens': calibration['lens']}, endpoint='/api/v1/images/calibrate').json()
    assert explicit['calibration']['lens'] is None


def test_server_camera_routes_use_the_same_automatic_and_locked_correction(client, application, barrel_frame, monkeypatch):
    raw, _ = barrel_frame
    monkeypatch.setattr(application.state.camera, 'capture', lambda: (raw.copy(), datetime.now(timezone.utc)))
    calibrated = client.post('/api/v1/camera/calibrate', json={})
    assert calibrated.status_code == 200
    calibration = calibrated.json()['calibration']
    assert calibration['lens'] is not None
    response = client.post('/api/v1/camera/detect', json={'calibration': calibration})
    assert response.status_code == 200
    assert response.json()['source']['kind'] == 'camera'
    assert response.json()['source']['lens_corrected'] is True
    assert response.json()['calibration'] == calibration
    assert len(response.json()['detection']['balls']) >= 10
