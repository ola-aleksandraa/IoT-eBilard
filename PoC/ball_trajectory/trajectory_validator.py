"""
trajectory_validator.py — Check for collisions along a trajectory (Validation).
"""

import numpy as np
from geometry import (
    normalize, point_to_segment_distance, ball_blocks_segment,
    segment_to_segment_distance, ray_segment_intersection
)
from config import settings


def is_path_blocked(seg_p1, seg_p2, balls, ball_radius, exclude_indices=()):
    """Check if the path is blocked by another ball."""
    val_cfg = settings.module3_physics.trajectory_validation

    for i, ball in enumerate(balls):
        if i in exclude_indices:
            continue
        if ball_blocks_segment(
                np.array([ball.center_x, ball.center_y], dtype=float),
                float(ball.radius) + ball_radius + val_cfg.clearance_margin,
                seg_p1, seg_p2
        ):
            return True, i
    return False, -1


def is_cutting_cushion(seg_p1, seg_p2, table_layout, ball_r):
    """Check if the ball path accidentally cuts through a corner cushion."""
    val_cfg = settings.module3_physics.trajectory_validation

    threshold = ball_r - val_cfg.cushion_cut_margin_lo
    for name, cp1, cp2 in table_layout.solid_cushions:
        d_seg = segment_to_segment_distance(seg_p1, seg_p2, cp1, cp2)
        if d_seg < threshold:
            if d_seg < ball_r * val_cfg.cushion_cut_margin_hi:
                d1 = point_to_segment_distance(seg_p1, cp1, cp2)
                d2 = point_to_segment_distance(seg_p2, cp1, cp2)
                mid = (np.array(seg_p1, dtype=float) + np.array(seg_p2, dtype=float)) / 2.0
                d_mid = point_to_segment_distance(mid, cp1, cp2)

                rail_threshold_hi = ball_r * val_cfg.cushion_cut_margin_hi
                rail_threshold_lo = ball_r * val_cfg.cushion_cut_margin_lo

                if (rail_threshold_lo < d1 < rail_threshold_hi and
                        rail_threshold_lo < d2 < rail_threshold_hi and
                        rail_threshold_lo < d_mid < rail_threshold_hi):
                    continue
            return True, name
    return False, None


def trace_to_cushion(start, direction, table_layout, max_dist=None):
    """Trace a ray from the start point until it hits a cushion (used for the deflect direction)."""
    # If max_dist is not provided, use the default from config (direct shot deflect)
    if max_dist is None:
        max_dist = settings.module3_physics.trajectory_validation.deflect_trace_direct

    start = np.array(start, dtype=float)
    direction = normalize(np.array(direction, dtype=float))

    best_t = max_dist
    best_pt = start + direction * max_dist

    for name, p1, p2 in table_layout.cushions:
        pt, t = ray_segment_intersection(start, direction, p1, p2)
        if pt is not None and 1.0 < t < best_t:
            best_t = t
            best_pt = pt

    if best_t >= max_dist:
        diagonal = (table_layout.width ** 2 + table_layout.height ** 2) ** 0.5
        capped_dist = min(max_dist, diagonal * 0.6)
        best_pt = start + direction * capped_dist

    return best_pt