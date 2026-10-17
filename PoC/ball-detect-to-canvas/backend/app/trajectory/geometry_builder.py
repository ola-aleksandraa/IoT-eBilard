"""Builds TableStaticGeometry (pockets, pocket gates, cushions, normals) from the table corners."""
import numpy as np

from .geometry import dist
from .table_types import TableStaticGeometry


def sort_corners(corners: np.ndarray) -> np.ndarray:
    """Order 4 corners as [TL, TR, BR, BL] (image coordinates, y grows downwards)."""
    centroid = corners.mean(axis=0)
    angles = np.arctan2(corners[:, 1] - centroid[1], corners[:, 0] - centroid[0])
    order = np.argsort(angles)
    return corners[order]


def build_static_geometry(inner_corners, ball_radius: float | None = None) -> TableStaticGeometry:
    corners = sort_corners(np.array(inner_corners, dtype=float))
    tl, tr, br, bl = corners

    width = (dist(tl, tr) + dist(bl, br)) / 2.0
    height = (dist(tl, bl) + dist(tr, br)) / 2.0
    if ball_radius is None:
        ball_radius = min(width, height) * 0.0225

    pockets = [tl, (tl + tr) / 2.0, tr, bl, (bl + br) / 2.0, br]

    W, H = width, height
    v_top = (tr - tl) / max(dist(tl, tr), 1e-9)
    v_right = (br - tr) / max(dist(tr, br), 1e-9)
    v_bottom = (bl - br) / max(dist(br, bl), 1e-9)
    v_left = (tl - bl) / max(dist(bl, tl), 1e-9)

    k_corner_h = (2.4 * ball_radius) / max(W, 1)
    k_corner_v = (2.1 * ball_radius) / max(H, 1)
    k_middle = (2.0 * ball_radius) / max(W, 1)

    gates = [
        (tl + v_top * W * k_corner_h, tl - v_left * H * k_corner_v),
        ((tl + tr) / 2.0 - v_top * W * k_middle, (tl + tr) / 2.0 + v_top * W * k_middle),
        (tr - v_top * W * k_corner_h, tr + v_right * H * k_corner_v),
        (bl - v_bottom * W * k_corner_h, bl + v_left * H * k_corner_v),
        ((bl + br) / 2.0 + v_bottom * W * k_middle, (bl + br) / 2.0 - v_bottom * W * k_middle),
        (br + v_bottom * W * k_corner_h, br - v_right * H * k_corner_v),
    ]

    solid_cushions = [
        ("top_left", gates[0][0], gates[1][0]),
        ("top_right", gates[1][1], gates[2][0]),
        ("right", gates[2][1], gates[5][1]),
        ("bottom_right", gates[5][0], gates[4][1]),
        ("bottom_left", gates[4][0], gates[3][0]),
        ("left", gates[3][1], gates[0][1]),
    ]

    cushions = [("top", tl, tr), ("right", tr, br), ("bottom", br, bl), ("left", bl, tl)]

    centroid = corners.mean(axis=0)
    cushion_normals = []
    for name, p1, p2 in cushions:
        edge = p2 - p1
        n = np.array([-edge[1], edge[0]])
        n = n / (np.linalg.norm(n) + 1e-9)
        if np.dot(n, centroid - (p1 + p2) / 2.0) < 0:  # normal must point into the table
            n = -n
        cushion_normals.append((name, n))

    return TableStaticGeometry(
        width=width, height=height, ball_radius=float(ball_radius), corners=corners,
        pockets=pockets, pocket_gates=gates, cushions=cushions,
        cushion_normals=cushion_normals, solid_cushions=solid_cushions,
    )
