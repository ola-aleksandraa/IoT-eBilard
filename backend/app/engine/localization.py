"""Find round ball silhouettes in camera pixels, before planar rectification.

A sphere stays approximately round in a pinhole image. Warping the cloth plane
first stretches that silhouette, particularly in end-on tournament views.
"""

import math

import cv2
import numpy as np
from .opencv_compat import find_contours


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
    maxima = (
        distance >= cv2.dilate(distance, np.ones((span, span), np.uint8)) - 0.01
    ) & (distance > expected * 0.58)
    count, labels = cv2.connectedComponents(np.uint8(maxima))
    peaks = []
    for label in range(1, count):
        ys, xs = np.where(labels == label)
        peaks.append(
            (float(xs.mean()), float(ys.mean()), float(distance[ys, xs].max()))
        )
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
        contours, _ = find_contours(
            region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours:
            candidate = fit_candidate(
                max(contours, key=cv2.contourArea), expected, "watershed"
            )
            if candidate:
                result.append(candidate)
    return result


def locate_source(image, source_points, homography, width, height, settings):
    scale = min(1.0, 1280 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale)
    h, w = small.shape[:2]
    polygon = np.float32(source_points * scale)
    area = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(area, np.int32(polygon), 255)
    inverse = np.linalg.inv(homography)
    physical_radius = height * settings.ball_radius_ratio

    def expected_at(x, y):
        table = cv2.perspectiveTransform(
            np.float32([[[x / scale, y / scale]]]), homography
        )[0, 0]
        probes = np.float32(
            [[table, table + [physical_radius, 0], table + [0, physical_radius]]]
        )
        mapped = cv2.perspectiveTransform(probes, inverse)[0] * scale
        return max(
            2.0,
            float(
                np.linalg.svd(
                    np.stack([mapped[1] - mapped[0], mapped[2] - mapped[0]], axis=1),
                    compute_uv=False,
                )[0]
            ),
        )

    center = polygon.mean(axis=0)
    radii = [
        expected_at(*point) for point in [center, *(center + 0.75 * (polygon - center))]
    ]
    low, high = max(2, int(min(radii) * 0.55)), max(4, int(max(radii) * 1.5))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    cloth_pixels = hsv[area > 0]
    colorful = cloth_pixels[(cloth_pixels[:, 1] > 50) & (cloth_pixels[:, 2] > 40)]
    median_s = float(np.median(cloth_pixels[:, 1]))
    median_v = float(np.median(cloth_pixels[:, 2]))
    foreground = np.zeros((h, w), bool)
    hue = None
    if median_s > 45 and len(colorful) > 100:
        histogram = np.bincount(colorful[:, 0], minlength=180).astype(float)
        histogram = sum(np.roll(histogram, i) for i in range(-3, 4))
        hue = (
            settings.cloth_hue
            if settings.cloth_hue is not None
            else int(histogram.argmax())
        )
        delta = np.abs(hsv[:, :, 0].astype(float) - hue)
        delta = np.minimum(delta, 180 - delta)
        foreground = (
            (delta > settings.hue_tolerance)
            | (hsv[:, :, 1] < max(settings.saturation_min, median_s * 0.60))
            | (hsv[:, :, 2] < median_v * 0.40)
        )
    # Local LAB contrast also recovers blue-on-blue balls and neutral cloth.
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    kernel = max(9, min(81, int(np.median(radii) * 4) | 1))
    background = cv2.medianBlur(lab, kernel)
    difference = np.abs(lab.astype(float) - background.astype(float))
    foreground |= (difference[:, :, 0] > 16) | (
        np.linalg.norm(difference[:, :, 1:], axis=2) > 12
    )
    mask = np.uint8(foreground & (area > 0)) * 255
    kernel3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel3)
    contours, _ = find_contours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(mask, contours, -1, 255, cv2.FILLED)
    mask[area == 0] = 0
    candidates = []
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    for label in range(1, count):
        x, y, bw, bh, size = stats[label]
        expected = expected_at(*centers[label])
        if size < math.pi * (expected * 0.5) ** 2 or size > math.pi * expected**2 * 24:
            continue
        component = np.uint8(labels[y : y + bh, x : x + bw] == label) * 255
        component = cv2.copyMakeBorder(
            component, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0
        )
        outlines, _ = find_contours(
            component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        candidate = fit_candidate(
            max(outlines, key=cv2.contourArea), expected, "source-contour"
        )
        local = [candidate] if candidate else []
        if settings.split_touching and size > math.pi * expected**2 * 1.4:
            separated = split_component(component, expected)
            if len(separated) > 1:
                local = separated
        for cx, cy, radius, score, method in local:
            candidates.append((cx + x - 2, cy + y - 2, radius, score, method))

    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0.8)
    gray[area == 0] = round(median_v * 0.6)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=max(4, low * 1.5),
        param1=65,
        param2=13,
        minRadius=low,
        maxRadius=min(high, min(h, w) // 8),
    )
    if circles is not None:
        edges = cv2.dilate(cv2.Canny(gray, 30, 65), np.ones((3, 3), np.uint8))
        angles = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        for x, y, radius in circles[0]:
            if area[round(y), round(x)] == 0:
                continue
            expected = expected_at(x, y)
            if not 0.60 * expected <= radius <= 1.45 * expected:
                continue
            xs = np.clip(np.round(x + radius * np.cos(angles)).astype(int), 0, w - 1)
            ys = np.clip(np.round(y + radius * np.sin(angles)).astype(int), 0, h - 1)
            support = float(np.mean(edges[ys, xs] > 0))
            inner_x = np.clip(
                np.round(x + radius * 0.50 * np.cos(angles)).astype(int), 0, w - 1
            )
            inner_y = np.clip(
                np.round(y + radius * 0.50 * np.sin(angles)).astype(int), 0, h - 1
            )
            occupancy = float(np.mean(mask[inner_y, inner_x] > 0))
            if support >= 0.60 and occupancy >= 0.35:
                candidates.append(
                    (float(x), float(y), float(radius), support * 1.02, "source-hough")
                )
    kept = []
    for x, y, radius, score, method in sorted(candidates, key=lambda p: -p[3]):
        table = cv2.perspectiveTransform(
            np.float32([[[x / scale, y / scale]]]), homography
        )[0, 0]
        # Reject pocket silhouettes at the six rail intersections.
        pockets = [
            (0, 0),
            (width / 2, 0),
            (width, 0),
            (0, height),
            (width / 2, height),
            (width, height),
        ]
        near_pocket = (
            min(np.hypot(table[0] - px, table[1] - py) for px, py in pockets)
            < physical_radius * 2.2
        )
        near_rail = (
            min(table[0], width - table[0], table[1], height - table[1])
            < physical_radius * 0.85
        )
        if near_pocket:
            angles = np.linspace(0, 2 * np.pi, 64, endpoint=False)
            xs = np.clip(
                np.round(x + radius * 1.5 * np.cos(angles)).astype(int), 0, w - 1
            )
            ys = np.clip(
                np.round(y + radius * 1.5 * np.sin(angles)).astype(int), 0, h - 1
            )
            cloth_support = np.mean((mask[ys, xs] == 0) & (area[ys, xs] > 0))
            if near_rail or cloth_support < 0.38:
                continue
        if not (0 <= table[0] <= width - 1 and 0 <= table[1] <= height - 1):
            continue
        if all(np.hypot(x - k[0], y - k[1]) > (radius + k[2]) * 0.65 for k in kept):
            kept.append((x, y, radius, score, method))
    return (
        [
            (x / scale, y / scale, r / scale, s, m)
            for x, y, r, s, m in sorted(kept, key=lambda p: (p[1], p[0]))
        ],
        mask,
        scale,
        hue,
    )


def orient_corners(image, corners):
    """Put the likely long edge first, before fixed-camera calibration locks.

    Estimate rectangular edge lengths with a centered, square-pixel pinhole
    camera. Nearly parallel vanishing directions do not constrain focal length;
    use a conservative focal estimate then. Manual corner ordering remains
    authoritative because this is called only for automatic suggestions.
    """
    h, w = image.shape[:2]
    points = np.float32([[p["x"] * (w - 1), p["y"] * (h - 1)] for p in corners])
    matrix = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), points
    )
    a, b = matrix[:, 0].copy(), matrix[:, 1].copy()
    a[:2] -= np.array([w / 2, h / 2]) * a[2]
    b[:2] -= np.array([w / 2, h / 2]) * b[2]
    focal = max(w, h) * 1.5
    constrained = all(
        abs(v[2]) > 0.03 * np.linalg.norm(v[:2]) / max(w, h) for v in (a, b)
    )
    if constrained:
        squared = -np.dot(a[:2], b[:2]) / (a[2] * b[2])
        if (0.5 * max(w, h)) ** 2 < squared < (3 * max(w, h)) ** 2:
            focal = math.sqrt(squared)
    a[:2] /= focal
    b[:2] /= focal
    return (
        corners[1:] + corners[:1]
        if np.linalg.norm(a) < 0.9 * np.linalg.norm(b)
        else corners
    )
