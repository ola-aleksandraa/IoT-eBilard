"""Table boundary estimation, with robust straight-edge extrapolation past pockets.

Multiple color masks accommodate colored and low-saturation cloth. No learned
models or reference-photo-specific coordinates are used.
"""
import cv2
import numpy as np


def ordered(points):
    center = points.mean(axis=0)
    points = points[np.argsort(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))]
    upper = np.argsort(points[:, 1])[:2]
    return np.roll(points, -upper[np.argmin(points[upper, 0])], axis=0)


def refine_edges(contour, quad, diagonal):
    boundary = contour[:, 0, :].astype(float)
    lines, residuals = [], []
    for i in range(4):
        a, b = quad[i], quad[(i + 1) % 4]
        direction = b - a; length = np.linalg.norm(direction); direction /= length
        relative = boundary - a
        along = relative @ direction
        perpendicular = np.abs(relative[:, 0] * direction[1] - relative[:, 1] * direction[0])
        # Ignore pockets and corner bevels; use the middle 76% of each edge.
        selected = boundary[(along > length * .12) & (along < length * .88) & (perpendicular < diagonal * .025)]
        if len(selected) < 12 or np.ptp(selected @ direction) < length * .35:
            return None
        vx, vy, x, y = cv2.fitLine(selected.astype(np.float32), cv2.DIST_HUBER, 0, .01, .01).ravel()
        distances = np.abs((selected[:, 0] - x) * vy - (selected[:, 1] - y) * vx)
        inliers = selected[distances <= max(1.5, float(np.quantile(distances, .70)))]
        if len(inliers) >= 10:
            vx, vy, x, y = cv2.fitLine(inliers.astype(np.float32), cv2.DIST_HUBER, 0, .01, .01).ravel()
            # Score the robust line on the same inliers used to fit it. Pocket
            # gaps, shadows and textured rail boundaries are excluded above;
            # charging their old residual again rejects otherwise straight rails.
            distances = np.abs((inliers[:, 0] - x) * vy - (inliers[:, 1] - y) * vx)
        lines.append(np.array([vy, -vx, vx * y - vy * x]))
        residuals.append(float(np.median(distances)))
    corners = []
    for i in range(4):
        crossing = np.cross(lines[i - 1], lines[i])
        if abs(crossing[2]) < .08:
            return None
        corners.append(crossing[:2] / crossing[2])
    return np.float32(corners), float(np.mean(residuals))


def candidate_masks(image, settings=None):
    image = cv2.GaussianBlur(image, (3, 3), 0)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    if settings is not None and settings.cloth_hue is not None:
        delta = np.abs(hsv[:, :, 0].astype(float) - settings.cloth_hue)
        delta = np.minimum(delta, 180 - delta)
        yield np.uint8((delta <= settings.hue_tolerance)
                       & (hsv[:, :, 1] >= settings.saturation_min)
                       & (hsv[:, :, 2] > 25)) * 255
        return
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(float)
    h, w = image.shape[:2]
    # Pale/grey cloth under spotlights can lose almost all hue information.
    for value in (75, 100, 120, 140, 170, 200):
        yield np.uint8((hsv[:, :, 1] < 90) & (hsv[:, :, 2] > value)) * 255
    sample = hsv[h // 8:h * 7 // 8:3, w // 8:w * 7 // 8:3].reshape(-1, 3)
    valid = sample[(sample[:, 1] > 50) & (sample[:, 2] > 45)]
    if len(valid):
        histogram = np.bincount(valid[:, 0], minlength=180).astype(float)
        histogram = sum(np.roll(histogram, k) for k in range(-3, 4))
        for _ in range(2):
            hue = int(histogram.argmax())
            if histogram[hue] < 50:
                break
            delta = np.abs(hsv[:, :, 0].astype(float) - hue); delta = np.minimum(delta, 180 - delta)
            for tolerance in (10, 18):
                yield np.uint8((delta <= tolerance) & (hsv[:, :, 1] > 45) & (hsv[:, :, 2] > 40)) * 255
            histogram[np.minimum(np.abs(np.arange(180) - hue), 180 - np.abs(np.arange(180) - hue)) < 25] = 0
    # Quantized LAB modes, not a single center pixel (which may be a ball).
    colors = lab[h // 5:h * 4 // 5:4, w // 5:w * 4 // 5:4].reshape(-1, 3)
    bins = (colors // np.array([24, 12, 12])).astype(int)
    keys, counts = np.unique(bins, axis=0, return_counts=True)
    seeds = []
    for key in keys[np.argsort(-counts)[:8]]:
        color = np.median(colors[np.all(bins == key, axis=1)], axis=0)
        if color[0] < 65 or any(np.linalg.norm((color - c) / [2, 1, 1]) < 15 for c in seeds):
            continue
        seeds.append(color)
        chroma = np.linalg.norm(lab[:, :, 1:] - color[1:], axis=2)
        for lightness in (24, 48):
            yield np.uint8((chroma < 18) & (np.abs(lab[:, :, 0] - color[0]) < lightness)) * 255
        if len(seeds) >= 3:
            break


def inner_cushion_edges(image, quad):
    """Find coherent parallel seams inward from the cloth-color silhouette.

    Median normal profiles ignore local balls, pocket gaps and printed marks.
    A visible inner cushion seam takes priority over the outer color boundary.
    """
    lab = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2LAB), (3, 3), 0).astype(np.float32)
    h, w = image.shape[:2]; diagonal = np.hypot(w, h)
    interior = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(interior, np.int32(quad.mean(axis=0) + .8 * (quad - quad.mean(axis=0))), 255)
    pale_cloth = np.median(cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1][interior > 0]) < 90
    lines = []
    for i in range(4):
        a, b = quad[i], quad[(i + 1) % 4]
        direction = (b - a) / np.linalg.norm(b - a)
        normal = np.array([-direction[1], direction[0]])
        ts = np.r_[np.linspace(.16, .39, 22), np.linspace(.61, .84, 22)]
        positions = a + ts[:, None] * (b - a)
        offsets = np.arange(-int(diagonal * .012), int(diagonal * .040) + 1, dtype=float)
        grid = positions[:, None, :] + offsets[None, :, None] * normal
        samples = cv2.remap(lab, grid[:, :, 0].astype(np.float32), grid[:, :, 1].astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        gradient = np.linalg.norm(samples[:, 4:] - samples[:, :-4], axis=2)
        profile = np.median(gradient, axis=0)
        # The innermost significant transition leads into the flat cloth plane.
        # Adjacent cushion seams can form one broad gradient band. The last
        # coherent peak leads onto the cloth; choosing the strongest peak in
        # the band can include the cushion face in the playing surface.
        threshold = max(4., float(profile.max()) * .12)
        strong = profile > threshold
        groups = np.split(np.flatnonzero(strong), np.where(np.diff(np.flatnonzero(strong)) > 1)[0] + 1)
        groups = [g for g in groups if len(g) and offsets[g[-1] + 2] < offsets[-1] - 2]
        if groups:
            group = groups[-1]
            peaks = [j for j in group if 0 < j < len(profile) - 1
                     and profile[j] >= profile[j - 1] and profile[j] >= profile[j + 1]]
            peak = peaks[-1] if peaks else group[np.argmax(profile[group])]
            low, high = max(0, peak - 2), min(gradient.shape[1], peak + 3)
            best = low + np.argmax(gradient[:, low:high], axis=1)
            valid = gradient[np.arange(len(best)), best] > max(4., profile[peak] * .5)
            points = positions[valid] + offsets[best[valid] + 2, None] * normal
            if len(points) >= 22:
                if pale_cloth:
                    # Achromatic thresholds may cut across a lighting gradient;
                    # use the photometric seam to correct that coarse angle.
                    vx, vy, x, y = cv2.fitLine(points.astype(np.float32), cv2.DIST_HUBER, 0, .01, .01).ravel()
                    lines.append(np.array([vy, -vx, vx * y - vy * x])); continue
                # Preserve the robust full-rail angle on colored cloth.
                offset = float(np.median(offsets[best[valid] + 2]))
                lines.append(np.array([normal[0], normal[1], -normal @ (a + offset * normal)])); continue
        lines.append(np.array([normal[0], normal[1], -normal @ a]))
    intersections = []
    for i in range(4):
        p = np.cross(lines[i - 1], lines[i])
        if abs(p[2]) < .08:
            return quad
        intersections.append(p[:2] / p[2])
    refined = np.float32(intersections)
    if not cv2.isContourConvex(refined) or cv2.contourArea(refined, oriented=True) < cv2.contourArea(quad) * .65:
        return quad
    return refined


def find_table(image, settings=None):
    height, width = image.shape[:2]
    scale = min(1, 1000 / max(width, height))
    small = cv2.resize(image, None, fx=scale, fy=scale)
    h, w = small.shape[:2]; diagonal = float(np.hypot(w, h))
    best = None
    for mask in candidate_masks(small, settings):
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:2]:
            area = cv2.contourArea(contour)
            if not .08 * h * w < area < .985 * h * w:
                continue
            hull = cv2.convexHull(contour)
            quad = None
            for epsilon in (.012, .020, .030, .045, .060):
                approximation = cv2.approxPolyDP(hull, epsilon * cv2.arcLength(hull, True), True)
                if len(approximation) == 4:
                    quad = ordered(approximation[:, 0, :].astype(float)); break
            if quad is None:
                continue
            refined = refine_edges(contour, quad, diagonal)
            if refined is None:
                continue
            points, residual = refined
            if not cv2.isContourConvex(points) or cv2.contourArea(points, oriented=True) <= 0:
                continue
            if np.any(points < -diagonal * .025) or np.any(points[:, 0] > w + diagonal * .025) or np.any(points[:, 1] > h + diagonal * .025):
                continue
            lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
            if min(lengths) < diagonal * .1:
                continue
            polygon = np.zeros_like(mask); cv2.fillConvexPoly(polygon, np.int32(points), 255)
            coverage = np.count_nonzero((mask > 0) & (polygon > 0)) / max(1, np.count_nonzero(polygon))
            convexity = min(1., area / max(1, cv2.contourArea(hull)))
            straightness = float(np.exp(-residual / 2))
            if coverage < .78 or convexity < .80 or straightness < .35:
                continue
            score = .40 * coverage + .25 * convexity + .25 * straightness + .10 * min(1, area / (h * w) * 2)
            if best is None or score > best[0]:
                best = (score, points)
    if best is None:
        return None
    score, points = best
    points = inner_cushion_edges(small, points)
    normalized = [{"x": float(np.clip(x / scale / (width - 1), 0, 1)), "y": float(np.clip(y / scale / (height - 1), 0, 1))} for x, y in points]
    return {"corners": normalized, "quality": float(round(score, 3)), "method": "color consensus + robust edge intersections"}
