"""CPU-only, single-frame pipeline. No weights, training, or temporal identities."""

import base64
import math
from time import perf_counter

import cv2
import numpy as np

from .models import Ball, DetectionRequest, Settings

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
    return result["corners"] if result else None


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


def fit_candidate(contour, expected, method):
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0 or area < math.pi * (expected * 0.60) ** 2:
        return None
    circularity = 4 * math.pi * area / perimeter**2
    (x, y), radius = cv2.minEnclosingCircle(contour)
    _, _, width, height = cv2.boundingRect(contour)
    if not (expected * 0.62 <= radius <= expected * 1.48):
        return None
    if circularity < 0.55 or max(width, height) / max(1, min(width, height)) > 1.65:
        return None
    return (float(x), float(y), float(radius), float(circularity), method)


def split_component(component, expected):
    """Seed local distance maxima, then watershed the foreground silhouette.

    A flat interior avoids gradient rings around unequal distance peaks stealing
    an entire touching region. The silhouette boundary constrains the flood.
    """
    distance = cv2.distanceTransform(component, cv2.DIST_L2, 5)
    span = max(3, int(expected * 1.15) | 1)
    maxima = (distance >= cv2.dilate(distance, np.ones((span, span), np.uint8)) - 0.01) & (distance > expected * 0.58)
    count, labels = cv2.connectedComponents(np.uint8(maxima))
    peaks = []
    for label in range(1, count):
        ys, xs = np.where(labels == label)
        peaks.append((float(xs.mean()), float(ys.mean()), float(distance[ys, xs].max())))
    seeds = []
    for x, y, value in sorted(peaks, key=lambda p: -p[2]):
        if all(math.hypot(x - sx, y - sy) > expected * 1.25 for sx, sy, _ in seeds):
            seeds.append((x, y, value))
    if not 2 <= len(seeds) <= 20:
        return []
    markers = np.zeros(component.shape, np.int32)
    markers[component == 0] = 1
    for label, (x, y, _) in enumerate(seeds, 2):
        cv2.circle(markers, (round(x), round(y)), 2, label, -1)
    cv2.watershed(cv2.cvtColor(component, cv2.COLOR_GRAY2BGR), markers)
    result = []
    for label in range(2, len(seeds) + 2):
        region = np.uint8((markers == label) & (component > 0)) * 255
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            candidate = fit_candidate(max(contours, key=cv2.contourArea), expected, "watershed")
            if candidate:
                result.append(candidate)
    return result


def locate(image, mask, expected, split_touching):
    candidates = []
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if area < math.pi * (expected * 0.55) ** 2 or area > math.pi * expected**2 * 24:
            continue
        component = np.uint8(labels[y:y + height, x:x + width] == label) * 255
        component = cv2.copyMakeBorder(component, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
        contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidate = fit_candidate(max(contours, key=cv2.contourArea), expected, "contour")
        local = [candidate] if candidate else []
        if split_touching and area > math.pi * expected**2 * 1.4:
            separated = split_component(component, expected)
            if len(separated) > 1:
                local = separated
        for cx, cy, radius, score, method in local:
            candidates.append((cx + x - 2, cy + y - 2, radius, score, method))

    # Independent image edges can recover balls similar in hue to the cloth.
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 1)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=expected * 1.35,
                               param1=80, param2=19, minRadius=max(3, round(expected * 0.65)), maxRadius=round(expected * 1.4))
    if circles is not None:
        edges = cv2.Canny(gray, 35, 80)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
        height, width = mask.shape
        angles = np.linspace(0, math.tau, 48, endpoint=False)
        for x, y, radius in circles[0]:
            xs = np.clip(np.round(x + radius * np.cos(angles)).astype(int), 0, width - 1)
            ys = np.clip(np.round(y + radius * np.sin(angles)).astype(int), 0, height - 1)
            coverage = float(np.mean(edges[ys, xs] > 0))
            if coverage >= 0.65:
                candidates.append((float(x), float(y), float(radius), coverage * 0.85, "hough"))
    kept = []
    height, width = mask.shape
    for candidate in sorted(candidates, key=lambda p: -p[3]):
        x, y, radius, _, _ = candidate
        if not (radius * 0.9 < x < width - radius * 0.9 and radius * 0.9 < y < height - radius * 0.9):
            continue
        if all(math.hypot(x - k[0], y - k[1]) > (radius + k[2]) * 0.65 for k in kept):
            kept.append(candidate)
    return sorted(kept, key=lambda p: (p[1], p[0]))


def classify(image, x, y, radius):
    height, width = image.shape[:2]
    left, top = max(0, int(x - radius)), max(0, int(y - radius))
    right, bottom = min(width, math.ceil(x + radius + 1)), min(height, math.ceil(y + radius + 1))
    roi = image[top:bottom, left:right]
    yy, xx = np.mgrid[top:bottom, left:right]
    disk = (xx - x)**2 + (yy - y)**2 < (radius * 0.83)**2
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 155) & disk
    dark = (hsv[:, :, 2] < 70) & disk
    colored = (hsv[:, :, 1] > 75) & (hsv[:, :, 2] > 65) & disk
    pixels = max(1, np.count_nonzero(disk))
    wf, df, cf = [np.count_nonzero(m) / pixels for m in (white, dark, colored)]
    outer = disk & ((xx - x)**2 + (yy - y)**2 > (radius * 0.48)**2)
    sectors = ((np.arctan2(yy - y, xx - x) + math.pi) / (math.tau / 8)).astype(int) % 8
    white_sectors = sum(np.count_nonzero(white & outer & (sectors == i)) / max(1, np.count_nonzero(outer & (sectors == i))) > 0.25 for i in range(8))
    if wf >= 0.80:
        kind, score, reason = "cue", min(0.97, wf), "Predominantly bright, low-saturation surface."
    elif df >= 0.72 and cf < 0.12:
        kind, score, reason = "eight", min(0.94, df), "Predominantly dark surface with little saturated color."
    elif 0.22 <= wf < 0.78 and cf >= 0.20 and white_sectors >= 3:
        kind, score, reason = "striped", 0.78, "Broad white areas reach several outer sectors around a colored band."
    elif wf < 0.20 and cf >= 0.55:
        kind, score, reason = "solid", 0.76, "Mostly saturated color; visible white area is small. A hidden stripe remains possible."
    else:
        kind, score, reason = "unknown", 0.35, "Visible color and white-area pattern do not clearly identify a ball type."
    if kind == "cue":
        color = "#f4f1e8"
    elif kind == "eight":
        color = "#252a31"
    elif np.any(colored):
        b, g, r = np.median(roi[colored], axis=0).astype(int)
        color = f"#{r:02x}{g:02x}{b:02x}"
    else:
        color = "#8c969e"
    return kind, score, reason, color, round(wf, 3)


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
    warped = cv2.warpPerspective(image, homography, (width, height))
    mask, hue = object_mask(warped, settings)
    expected = height * settings.ball_radius_ratio
    candidates = locate(warped, mask, expected, settings.split_touching)
    inverse = np.linalg.inv(homography)
    balls = []
    overlay = warped.copy()
    for index, (x, y, radius, _, method) in enumerate(candidates, 1):
        kind, confidence, reason, color, white_fraction = classify(warped, x, y, radius)
        source = cv2.perspectiveTransform(np.float32([[[x, y]]]), inverse)[0, 0]
        balls.append(Ball(id=index, kind=kind, x=round(x / (width - 1), 5), y=round(y / (height - 1), 5),
                          radius=round(radius / height, 5), source_x=round(float(source[0]) / (source_w - 1), 5),
                          source_y=round(float(source[1]) / (source_h - 1), 5), color=color, confidence=confidence,
                          reason=reason, white_fraction=white_fraction, method=method).model_dump())
        cv2.circle(overlay, (round(x), round(y)), round(radius + 3), (120, 255, 196), 2, cv2.LINE_AA)
        cv2.putText(overlay, str(index), (round(x + radius + 4), round(y - radius)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 255, 240), 1, cv2.LINE_AA)
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
