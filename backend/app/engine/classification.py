"""Deterministic appearance rules. No learned weights or ball-number recognition."""

import cv2
import numpy as np

PALETTE = {
    "cue": "#faf8ef",
    "eight": "#202429",
    "solid": "#e3ad48",
    "striped": "#e3ad48",
    "unknown": "#87949c",
}


def white_balance(image, cloth_polygon=None):
    """Estimate the illuminant from bright, weakly saturated pixels on the table.

    Cue surfaces and white patches contribute; the hue of colored cloth does
    not. This corrects broadcast color casts without using any class labels.
    """
    scale = min(1.0, 640 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    area = np.ones(small.shape[:2], np.uint8)
    if cloth_polygon is not None:
        area[:] = 0
        cv2.fillConvexPoly(area, np.int32(np.array(cloth_polygon) * scale), 1)
    # Pale turquoise cloth is bright and moderately desaturated too. Including
    # it in the illuminant estimate washes pale colored balls into cue-white.
    bright = (area > 0) & (hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 160)
    if np.count_nonzero(bright) < 20:
        return np.ones(3)
    values = small[bright].astype(float)
    values = values[values.max(axis=1) >= np.percentile(values.max(axis=1), 65)]
    chromaticity = np.median(values / values.max(axis=1, keepdims=True), axis=0)
    return np.clip(1 / np.maximum(chromaticity, 0.65), 1, 1.5)


def appearance(image, x, y, radius, balance=None):
    height, width = image.shape[:2]
    left, top = max(0, int(x - radius)), max(0, int(y - radius))
    right, bottom = (
        min(width, int(np.ceil(x + radius + 1))),
        min(height, int(np.ceil(y + radius + 1))),
    )
    roi = image[top:bottom, left:right]
    corrected = np.uint8(
        np.clip(
            roi.astype(float) * (np.ones(3) if balance is None else balance), 0, 255
        )
    )
    hsv = cv2.cvtColor(corrected, cv2.COLOR_BGR2HSV)
    yy, xx = np.mgrid[top:bottom, left:right]
    radial = ((xx - x) ** 2 + (yy - y) ** 2) / max(1, radius**2)
    disk = radial < 0.84**2
    pixels = max(1, np.count_nonzero(disk))
    saturation, value = hsv[:, :, 1], hsv[:, :, 2]
    white = disk & (saturation < 60) & (value > 110)
    dark = disk & (value < 100)
    colored = disk & (saturation >= 65) & (value >= 100)
    wf, df, cf = [np.count_nonzero(m) / pixels for m in (white, dark, colored)]
    outer = disk & (radial > 0.50**2)
    outer_white = np.count_nonzero(white & outer) / max(1, np.count_nonzero(outer))
    sectors = ((np.arctan2(yy - y, xx - x) + np.pi) * 6 / np.pi).astype(int) % 12
    sector_white = [
        float(np.mean(white[outer & (sectors == i)]))
        if np.any(outer & (sectors == i))
        else 0.0
        for i in range(12)
    ]
    white_sectors = sum(v > 0.25 for v in sector_white)
    opposed = any(
        sector_white[i] > 0.20 and sector_white[(i + 6) % 12] > 0.20 for i in range(6)
    )
    core = radial < 0.45**2
    core_white = np.count_nonzero(white & core) / max(1, np.count_nonzero(core))
    bright_value = float(np.percentile(value[disk], 90))
    ink = np.count_nonzero(core & (value < bright_value * 0.65)) / max(
        1, np.count_nonzero(core)
    )
    median_value = float(np.median(value[disk]))
    chroma = corrected.max(axis=2).astype(float) - corrected.min(axis=2)
    dark_chroma = float(np.median(chroma[disk & (value <= median_value)]))
    return {
        "white": wf,
        "dark": df,
        "colored": cf,
        "outer_white": outer_white,
        "sectors": white_sectors,
        "opposed": opposed,
        "median_value": median_value,
        "dark_chroma": dark_chroma,
        "core_white": core_white,
        "ink": ink,
    }


def classify(image, x, y, radius, balance=None):
    return classify_features(appearance(image, x, y, radius, balance))


def classify_features(f):
    wf, df, cf = f["white"], f["dark"], f["colored"]
    if (
        (wf >= 0.78 and cf < 0.14 and df < 0.12)
        or (wf > 0.58 and f["core_white"] > 0.92 and cf < 0.40 and df < 0.20)
    ) and f["ink"] < 0.12:
        kind, score, reason = (
            "cue",
            min(0.98, 0.65 + 0.30 * wf - 0.30 * f["ink"]),
            "Broad neutral white surface, allowing small cue-ball spots.",
        )
    elif (
        df >= 0.45
        and f["median_value"] < 110
        and f["dark_chroma"] < 55
        and cf < 0.50
        and wf < 0.30
    ):
        kind, score, reason = (
            "eight",
            min(
                0.97,
                0.65 + 0.30 * df - 0.001 * f["median_value"] - 0.001 * f["dark_chroma"],
            ),
            "Predominantly dark body, allowing a white number patch and reflections.",
        )
    elif (
        wf >= 0.16
        and cf >= 0.10
        and f["outer_white"] >= 0.13
        and (
            wf >= 0.32
            or f["opposed"]
            or (f["sectors"] >= 4 and f["outer_white"] > 0.20)
        )
    ):
        kind, score, reason = (
            "striped",
            min(0.90, 0.62 + 0.4 * wf),
            "Broad white regions extend toward the rim around a colored body.",
        )
    elif cf >= 0.30 and wf < 0.32:
        kind, score, reason = (
            "solid",
            0.76,
            "Colored body with little broad white area; a small number patch is allowed.",
        )
    else:
        kind, score, reason = (
            "unknown",
            0.35,
            "The visible surface does not clearly separate full, half, white, or black.",
        )
    return kind, round(score, 3), reason, PALETTE[kind], round(wf, 3)


def enforce_unique_specials(balls, features=None):
    """At most one cue and eight; never invent a missing/pocketed ball."""
    for kind in ("cue", "eight"):
        candidates = [b for b in balls if b["kind"] == kind]
        if len(candidates) < 2:
            continue
        winner = max(
            candidates,
            key=lambda b: (
                b["confidence"],
                b["white_fraction"] if kind == "cue" else -b["white_fraction"],
            ),
        )
        for ball in candidates:
            if ball is not winner:
                f = features[ball["id"] - 1] if features is not None else None
                fallback = "unknown"
                if (
                    f is not None
                    and kind == "cue"
                    and f["white"] > 0.25
                    and (f["colored"] > 0.05 or f["ink"] > 0.10)
                ):
                    fallback = "striped"
                elif (
                    f is not None
                    and kind == "eight"
                    and f["colored"] > 0.30
                    and f["white"] < 0.20
                ):
                    fallback = "solid"
                ball.update(
                    kind=fallback,
                    color=PALETTE[fallback],
                    confidence=0.50 if fallback != "unknown" else 0.35,
                    reason="Visible body pattern used after a stronger special-ball candidate was found elsewhere on the table.",
                )
    return balls
