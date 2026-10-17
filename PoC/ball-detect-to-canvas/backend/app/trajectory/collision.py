import numpy as np
import cv2
from .geometry import (
    normalize, dist, vec, dot,
    perpendicular_ccw, perpendicular_cw,
    angle_deg, length
)

from .config import settings


def compute_remaining_velocity(
        path_segments: list,
        cushion_count: int = 0,
        initial_velocity: float = None,
) -> float:
    # Get configuration from yaml
    phys_cfg = settings.module3_physics.physics
    init_vel = initial_velocity if initial_velocity is not None else phys_cfg.initial_velocity

    if not path_segments:
        return 0.0

    total_distance = sum(dist(p1, p2) for p1, p2 in path_segments)
    v_after_friction = init_vel * np.exp(-phys_cfg.friction_coeff * total_distance)
    v_remaining = v_after_friction * (phys_cfg.cushion_restitution ** cushion_count)

    return float(v_remaining)


# ─────────────────────────────────────────────────────────────
# GHOST BALL & DEFLECTION
# ─────────────────────────────────────────────────────────────

def compute_ghost_ball_for_pocket(target_pos, pocket_pos, ball_radius):
    target = np.array(target_pos, dtype=float)
    pocket = np.array(pocket_pos, dtype=float)
    target_exit_dir = normalize(pocket - target)
    ghost_pos = target - target_exit_dir * (2 * ball_radius)

    return ghost_pos, target_exit_dir


def compute_cue_deflection(cue_pos, ghost_pos, contact_dir):
    cue = np.array(cue_pos, dtype=float)
    ghost = np.array(ghost_pos, dtype=float)
    cue_travel_dir = normalize(ghost - cue)

    cross = cue_travel_dir[0] * contact_dir[1] - cue_travel_dir[1] * contact_dir[0]
    cut_angle = angle_deg(cue_travel_dir, contact_dir)

    if cross > 0:
        deflect_dir = perpendicular_cw(contact_dir)
    else:
        deflect_dir = perpendicular_ccw(contact_dir)
        cut_angle = -cut_angle

    deflect_dir = normalize(deflect_dir)
    return deflect_dir, cut_angle


class CollisionResult:
    def __init__(self):
        self.ghost_pos = None
        self.contact_dir = None
        self.target_exit_dir = None
        self.cue_deflect_dir = None
        self.cut_angle = 0.0
        self.is_valid = False


def compute_collision(cue_pos, target_pos, pocket_pos, ball_radius, table_layout=None):
    phys_cfg = settings.module3_physics.physics
    result = CollisionResult()

    cue = np.array(cue_pos, dtype=float)
    target = np.array(target_pos, dtype=float)
    pocket = np.array(pocket_pos, dtype=float)

    ghost_pos, contact_dir = compute_ghost_ball_for_pocket(target, pocket, ball_radius)
    result.ghost_pos = ghost_pos
    result.contact_dir = contact_dir
    result.target_exit_dir = contact_dir

    deflect_dir, cut_angle = compute_cue_deflection(cue, ghost_pos, contact_dir)
    result.cue_deflect_dir = deflect_dir
    result.cut_angle = cut_angle

    if table_layout is not None:
        pts = np.int32(table_layout.corners).reshape((-1, 1, 2))
        in_bounds = cv2.pointPolygonTest(pts, (float(ghost_pos[0]), float(ghost_pos[1])), False) >= 0
    else:
        in_bounds = True
        
    angle_ok  = abs(cut_angle) <= phys_cfg.max_cut_angle_deg
    result.is_valid = in_bounds and angle_ok

    return result

def cut_angle_difficulty(cut_angle_deg):
    max_angle = settings.module3_physics.physics.max_cut_angle_deg
    angle = abs(cut_angle_deg)
    if angle >= max_angle:
        return 1.0
    return angle / max_angle