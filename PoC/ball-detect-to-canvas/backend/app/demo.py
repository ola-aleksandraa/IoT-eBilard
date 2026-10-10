"""Deterministic synthetic fixture, explicitly not evidence of real-camera accuracy."""

import cv2
import numpy as np

from .vision import image_url

DEMO_BALLS = [
    (205, 160, "cue", (235, 238, 240)),
    (465, 105, "solid", (35, 185, 245)),
    (735, 145, "striped", (48, 66, 213)),
    (565, 235, "eight", (25, 26, 28)),
    (275, 315, "solid", (184, 81, 46)),
    (685, 325, "striped", (186, 76, 63)),
    (435, 365, "solid", (43, 87, 224)),
    (820, 370, "solid", (156, 66, 143)),
    (490, 270, "solid", (32, 142, 233)),
    (517, 270, "solid", (161, 63, 119)),
    (145, 390, "striped", (38, 174, 235)),
    (855, 215, "solid", (47, 91, 171)),
]


def make_demo():
    rng = np.random.default_rng(42)
    table = np.full((500, 1000, 3), (109, 118, 27), np.float32)
    table += rng.normal(0, 1.1, table.shape[:2])[:, :, None]
    table *= np.linspace(0.90, 1.07, 1000)[None, :, None]
    table = np.uint8(np.clip(table, 0, 255))
    for x, y, kind, color in DEMO_BALLS:
        cv2.ellipse(table, (x + 4, y + 5), (16, 12), 0, 0, 360, (75, 83, 20), -1, cv2.LINE_AA)
        cv2.circle(table, (x, y), 14, (20, 35, 30), -1, cv2.LINE_AA)
        cv2.circle(table, (x, y), 13, color, -1, cv2.LINE_AA)
        if kind == "striped":
            yy, xx = np.ogrid[:500, :1000]
            white = ((xx - x)**2 + (yy - y)**2 <= 13**2) & (np.abs(yy - y) > 5)
            table[white] = (230, 234, 237)
        elif kind in ("solid", "eight"):
            cv2.circle(table, (x + 1, y), 4, (224, 228, 232), -1, cv2.LINE_AA)
            if kind == "eight":
                cv2.putText(table, "8", (x - 2, y + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.20, (35, 35, 35), 1, cv2.LINE_AA)
        cv2.circle(table, (x - 4, y - 5), 2, (248, 249, 250), -1, cv2.LINE_AA)

    # A thin cue fragment tests rejection of long, non-circular objects.
    cv2.line(table, (15, 215), (110, 250), (141, 181, 198), 5, cv2.LINE_AA)
    source_corners = np.float32([[175, 140], [1010, 105], [1130, 665], [65, 630]])
    target_corners = np.float32([[0, 0], [999, 0], [999, 499], [0, 499]])
    transform = cv2.getPerspectiveTransform(target_corners, source_corners)
    image = np.full((760, 1200, 3), (24, 32, 36), np.uint8)
    rail = np.float32([[132, 104], [1040, 66], [1188, 710], [10, 675]])
    cv2.fillConvexPoly(image, rail.astype(int), (45, 58, 63), cv2.LINE_AA)
    cv2.polylines(image, [rail.astype(int)], True, (66, 82, 88), 3, cv2.LINE_AA)
    cloth = cv2.warpPerspective(table, transform, (1200, 760))
    mask = cv2.warpPerspective(np.full((500, 1000), 255, np.uint8), transform, (1200, 760))
    image[mask > 0] = cloth[mask > 0]
    for px, py in [*source_corners, (source_corners[0] + source_corners[1]) / 2, (source_corners[2] + source_corners[3]) / 2]:
        cv2.circle(image, (round(float(px)), round(float(py))), 17, (13, 20, 22), -1, cv2.LINE_AA)
    calibration = {"corners": [{"x": float(x / 1199), "y": float(y / 759)} for x, y in source_corners], "image_width": 1200, "image_height": 760}
    return image, calibration


def demo_response():
    image, calibration = make_demo()
    return {"image": image_url(image, png=True), "width": 1200, "height": 760, "calibration": calibration,
            "expected_count": len(DEMO_BALLS), "name": "Synthetic practice layout", "synthetic": True}
