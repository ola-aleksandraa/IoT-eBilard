"""Different table setups use the same public contract, without scene presets."""

import cv2
import numpy as np
import pytest

from tests.test_api import assert_numerical, client, application, upload


def table_frame(ratio, radius, cloth, portrait=False):
    height, width = round(1000 / ratio), 1000
    table = np.full((height, width, 3), cloth, np.uint8)
    r = round(radius * height)
    positions = [(.2, .4, (240, 240, 240)), (.55, .3, (25, 200, 240)),
                 (.65, .7, (20, 20, 20)), (.8, .45, (200, 60, 180))]
    for index, (x, y, color) in enumerate(positions):
        center = (round(x * (width - 1)), round(y * (height - 1)))
        cv2.circle(table, center, r, color, -1)
        if index == 3:
            yy, xx = np.ogrid[:height, :width]
            caps = ((xx - center[0]) ** 2 + (yy - center[1]) ** 2 <= r ** 2) & (np.abs(yy - center[1]) > r * .4)
            table[caps] = 240
        elif index in (1, 2):
            cv2.circle(table, center, max(2, round(r * .25)), (235, 235, 235), -1)
    corners = np.float32([[130, 100], [1070, 120], [1110, 680], [80, 650]])
    transform = cv2.getPerspectiveTransform(np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]), corners)
    frame = np.full((780, 1200, 3), 30, np.uint8)
    warped = cv2.warpPerspective(table, transform, (1200, 780))
    mask = cv2.warpPerspective(np.full((height, width), 255, np.uint8), transform, (1200, 780))
    frame[mask > 0] = warped[mask > 0]
    if portrait:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    return frame, positions


@pytest.mark.parametrize("ratio,radius", [(1.5, .035), (2, .026), (2.5, .018)])
@pytest.mark.parametrize("cloth", [(45, 125, 35), (155, 95, 20), (25, 35, 155), (160, 160, 160)])
def test_same_endpoints_across_table_proportions_ball_sizes_and_cloth(client, ratio, radius, cloth):
    frame, positions = table_frame(ratio, radius, cloth)
    data = cv2.imencode(".png", frame)[1].tobytes()
    settings = {"table_ratio": ratio, "ball_radius_ratio": radius}
    calibration = upload(client, data, {"settings": settings}, "/api/v1/images/calibrate")
    assert calibration.status_code == 200
    assert calibration.json()["table_status"] == "detected"
    response = upload(client, data, {"calibration": calibration.json()["calibration"], "settings": settings})
    assert response.status_code == 200, response.text
    result = response.json()["detection"]
    assert result["counts"] == {"total": 4, "cue": 1, "eight": 1, "solid": 1, "striped": 1, "unknown": 0}
    assert result["geometry"]["table_ratio"] == ratio
    for x, y, _ in positions:
        ball = min(result["balls"], key=lambda b: (b["x"] - x) ** 2 + (b["y"] - y) ** 2)
        assert [ball["x"], ball["y"]] == pytest.approx([x, y], abs=.015)
        assert ball["radius"] == radius
    layout = {"balls": result["balls"], "table_ratio": ratio}
    for endpoint in ("shots", "shots/predict", "shots/simulate"):
        options = layout if endpoint == "shots" else {**layout, "aim_x": .9, "aim_y": .3}
        shot = client.post("/api/v1/" + endpoint, json=options)
        assert shot.status_code == 200, shot.text
        assert shot.json()["status"] == "ok"
        assert_numerical(shot.json())


def test_portrait_camera_and_upload_share_geometry_and_settings(client, application, monkeypatch):
    frame, _ = table_frame(2, .026, (45, 125, 35), portrait=True)
    from datetime import datetime, timezone
    monkeypatch.setattr(application.state.camera, "capture", lambda: (frame, datetime.now(timezone.utc)))
    data = cv2.imencode(".png", frame)[1].tobytes()
    uploaded = upload(client, data).json()
    captured = client.post("/api/v1/camera/detect", json={}).json()
    assert uploaded["detection"]["counts"]["total"] == 4
    assert captured["detection"]["balls"] == uploaded["detection"]["balls"]
    assert captured["detection"]["geometry"] == uploaded["detection"]["geometry"]


def test_explicit_cloth_hue_selects_the_table_and_is_used_by_both_calibration_routes(client, application, monkeypatch):
    from datetime import datetime, timezone
    frame = np.full((700, 1200, 3), 25, np.uint8)
    cv2.rectangle(frame, (30, 50), (620, 650), (45, 125, 35), -1)
    cv2.rectangle(frame, (700, 150), (1150, 550), (155, 95, 20), -1)
    hue = int(cv2.cvtColor(np.uint8([[[155, 95, 20]]]), cv2.COLOR_BGR2HSV)[0, 0, 0])
    options = {"settings": {"cloth_hue": hue}}
    monkeypatch.setattr(application.state.camera, "capture", lambda: (frame, datetime.now(timezone.utc)))
    data = cv2.imencode(".png", frame)[1].tobytes()
    for body in (upload(client, data, options, "/api/v1/images/calibrate").json(),
                 client.post("/api/v1/camera/calibrate", json=options).json()):
        assert body["table_status"] == "detected"
        assert all(p["x"] > .55 for p in body["calibration"]["corners"])
