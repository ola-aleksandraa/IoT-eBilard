"""CPU-only, single-frame pipeline. No weights, training, or temporal identities."""

import base64
from time import perf_counter

import cv2
import numpy as np

from .models import Ball, DetectionRequest, Settings
from .classification import classify, appearance, classify_features, white_balance, enforce_unique_specials
from .localization import locate_source, orient_corners, split_component

OUTPUT_WIDTH = 1000


def image_url(image: np.ndarray, *, png=False) -> str:
    extension = ".png" if png else ".jpg"
    ok, buffer = cv2.imencode(extension, image, [] if png else [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("Could not encode the image.")
    return f"data:image/{'png' if png else 'jpeg'};base64," + base64.b64encode(buffer).decode()


def cloth_hue(hsv: np.ndarray) -> int:
    height, width = hsv.shape[:2]
    sample = hsv[height // 10 : height * 9 // 10, width // 10 : width * 9 // 10]
    valid = (sample[:, :, 1] > 55) & (sample[:, :, 2] > 40)
    hues = sample[:, :, 0][valid]
    if len(hues) < 100:
        raise ValueError("No dominant colored cloth found. Set a manual cloth hue or use a clearer image.")
    histogram = np.bincount(hues, minlength=180).astype(float)
    histogram = sum(np.roll(histogram, n) for n in range(-3, 4))
    return int(np.argmax(histogram))


def hue_distance(hue: np.ndarray, reference: int) -> np.ndarray:
    delta = np.abs(hue.astype(float) - reference)
    return np.minimum(delta, 180 - delta)


def suggest_corners(image: np.ndarray) -> list[dict] | None:
    from .calibration import find_table
    result = find_table(image)
    return orient_corners(image, result["corners"]) if result else None


def object_mask(image: np.ndarray, settings: Settings):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    if settings.cloth_hue is None and np.median(hsv[:, :, 1]) < 45:
        # Grey cloth and washed-out lighting have no meaningful hue. Compare
        # local luminance/chroma instead, retaining gradual illumination changes.
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        background = cv2.medianBlur(lab[:, :, 0], 51)
        light_difference = np.abs(lab[:, :, 0].astype(float) - background)
        chroma = np.linalg.norm(lab[:, :, 1:].astype(float) - np.median(lab[:, :, 1:], axis=(0, 1)), axis=2)
        cloth = (light_difference < 20) & (chroma < 20) & (hsv[:, :, 1] < max(60, float(np.median(hsv[:, :, 1])) + 40))
        hue = None
    else:
        hue = settings.cloth_hue if settings.cloth_hue is not None else cloth_hue(hsv)
        # Hue persists in cloth shadows. Ignore value except for nearly black regions.
        cloth = (hue_distance(hsv[:, :, 0], hue) <= settings.hue_tolerance) & (hsv[:, :, 1] >= settings.saturation_min) & (hsv[:, :, 2] > 25)
    mask = np.uint8(~cloth) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    # Fill white number-patch / specular holes without merging separate objects.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(mask, contours, -1, 255, cv2.FILLED)
    return mask, hue


def detect(image: np.ndarray, request: DetectionRequest, *, debug=True) -> dict:
    start = perf_counter()
    calibration, settings = request.calibration, request.settings
    source_h, source_w = image.shape[:2]
    if (source_w, source_h) != (calibration.image_width, calibration.image_height):
        raise ValueError("Calibration resolution differs from this image. Recalibrate or load a matching frame.")
    source_points = np.float32([[p.x * (source_w - 1), p.y * (source_h - 1)] for p in calibration.corners])
    width, height = OUTPUT_WIDTH, round(OUTPUT_WIDTH / settings.table_ratio)
    target_points = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    homography = cv2.getPerspectiveTransform(source_points, target_points)
    warped = cv2.warpPerspective(image, homography, (width, height)) if debug else None
    balance = white_balance(image, source_points)
    expected = height * settings.ball_radius_ratio
    candidates, source_mask, mask_scale, hue = locate_source(image, source_points, homography, width, height, settings)
    mask = cv2.warpPerspective(source_mask, homography @ np.diag([1/mask_scale, 1/mask_scale, 1]), (width, height), flags=cv2.INTER_NEAREST) if debug else None
    balls = []
    features = []
    overlay = warped.copy() if debug else None
    for index, (sx, sy, source_radius, _, method) in enumerate(candidates, 1):
        features.append(appearance(image, sx, sy, source_radius, balance))
        kind, confidence, reason, color, white_fraction = classify_features(features[-1])
        x, y = cv2.perspectiveTransform(np.float32([[[sx, sy]]]), homography)[0, 0]
        radius = expected
        source = [sx, sy]
        balls.append(Ball(id=index, kind=kind, x=round(x / (width - 1), 5), y=round(y / (height - 1), 5),
                          radius=round(radius / height, 5), source_x=round(float(source[0]) / (source_w - 1), 5),
                          source_y=round(float(source[1]) / (source_h - 1), 5), color=color, confidence=confidence,
                          reason=reason, white_fraction=white_fraction, method=method).model_dump())
        if debug:
            cv2.circle(overlay, (round(x), round(y)), round(radius + 3), (120, 255, 196), 2, cv2.LINE_AA)
            cv2.putText(overlay, str(index), (round(x + radius + 4), round(y - radius)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 255, 240), 1, cv2.LINE_AA)
    balls = enforce_unique_specials(balls, features)
    warnings = ["Classification scores are heuristic, not probabilities. Hidden stripes can resemble solids.",
                "Coordinates use the cloth plane; ball height causes parallax with an angled camera."]
    if not balls:
        warnings.insert(0, "No balls found. Check the corners, expected radius, and cloth threshold.")
    if len(balls) > 16:
        warnings.insert(0, "More than 16 candidates found; inspect reflections and adjust the expected radius.")
    if any(b["kind"] == "unknown" for b in balls):
        warnings.insert(0, "Some ball types are uncertain. Inspect the detections before using the layout.")
    return {"balls": balls, "table": {"width": width, "height": height, "ratio": settings.table_ratio},
            "cloth_hue": hue, "processing_ms": round((perf_counter() - start) * 1000, 1),
            "images": {"rectified": image_url(warped), "mask": image_url(mask, png=True), "overlay": image_url(overlay)} if debug else None,
            "homography": homography.tolist(), "warnings": warnings,
            "coordinate_system": "x: left→right, y: top→bottom, normalized [0,1]; radius relative to table height; IDs are frame-local"}
