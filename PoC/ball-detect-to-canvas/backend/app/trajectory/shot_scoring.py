"""
shot_scoring.py — Strategic shot scoring for billiards AI
Synchronized with TableStaticGeometry and TrackedBall.
"""

import numpy as np
from .geometry import dist, point_to_segment_distance
from .trajectory import ShotResult
from .config import settings


def clamp01(x):
    return float(np.clip(x, 0.0, 1.0))


# ============================================================
# POCKET PROBABILITY
# ============================================================
def score_cut_angle(cut_angle_deg):
    max_angle = settings.module3_physics.physics.max_cut_angle_deg
    angle = min(abs(float(cut_angle_deg)), max_angle)
    return float(np.cos(np.radians(angle)))


def score_shot_distance(total_path_length, max_path=None):
    if max_path is None:
        max_path = settings.module3_physics.scoring.constants.default_max_path
    return clamp01(1.0 - total_path_length / max_path)


def score_pocket_type(pocket_idx):
    pp_cfg = settings.module3_physics.scoring.pocket_probability
    # Pockets 1 and 4 are usually side pockets
    return pp_cfg.side_pocket_score if pocket_idx in {1, 4} else pp_cfg.corner_pocket_score


def score_target_proximity(target_pos, pocket_pos, table_diagonal):
    d = dist(target_pos, pocket_pos)
    return clamp01(1.0 - d / (table_diagonal * 0.5))


def score_path_clearance(shot, balls, ball_r):
    if not balls:
        return 1.0

    pp_cfg = settings.module3_physics.scoring.pocket_probability
    risk_radius = ball_r * pp_cfg.obstacle_radius_factor
    penalty = 0.0
    segments = []

    if len(shot.cue_path) >= 2:
        for i in range(len(shot.cue_path) - 1):
            segments.append((shot.cue_path[i], shot.cue_path[i + 1]))

    if len(shot.target_path) >= 2:
        for i in range(len(shot.target_path) - 1):
            segments.append((shot.target_path[i], shot.target_path[i + 1]))

    for i, ball in enumerate(balls):
        if i == shot.target_ball_idx or (hasattr(shot, 'cue_ball_idx') and i == shot.cue_ball_idx):
            continue

        p = np.array([ball.center_x, ball.center_y], dtype=float)
        for a, b in segments:
            d = point_to_segment_distance(p, a, b)
            if d < risk_radius:
                closeness = 1.0 - (d / risk_radius)
                penalty += pp_cfg.clearance_penalty_per_obstacle * closeness  # Local fine-tuning weight
                break

    penalty = min(penalty, pp_cfg.clearance_penalty_max)
    return clamp01(1.0 - penalty)


def compute_pocket_probability(shot, table_layout=None, balls=None):
    pp_cfg = settings.module3_physics.scoring.pocket_probability

    if table_layout:
        diagonal = (table_layout.width ** 2 + table_layout.height ** 2) ** 0.5
        max_path = diagonal * 2.0
    else:
        max_path = settings.module3_physics.scoring.constants.default_max_path

    target_pos = shot.target_path[0] if shot.target_path else shot.pocket_pos
    pocket_pos = shot.pocket_pos
    ball_r = float(balls[0].radius) if balls else 18.0

    score = (
            pp_cfg.w_cut_angle * score_cut_angle(shot.cut_angle) +
            pp_cfg.w_distance * score_shot_distance(shot.total_path_length, max_path) +
            pp_cfg.w_pocket_type * score_pocket_type(shot.pocket_idx) +
            pp_cfg.w_proximity * score_target_proximity(target_pos, pocket_pos, diagonal) +
            pp_cfg.w_clearance * score_path_clearance(shot, balls, ball_r)
    )
    return clamp01(score)


# ============================================================
# POSITION VALUE
# ============================================================
def score_collision_safety(shot, balls, ball_r):
    if not balls or len(shot.cue_path) < 2:
        return 1.0

    # Get coefficients from config (using obstacle_radius for collision zone and collision_risk_factor to divide risk)
    obstacle_factor = settings.module3_physics.scoring.pocket_probability.obstacle_radius_factor
    risk_factor = settings.module3_physics.scoring.position_value.collision_risk_factor

    risk_radius = ball_r * obstacle_factor
    cue_final = np.array(shot.cue_path[-1], dtype=float)
    min_dist = 999999.0

    for i, ball in enumerate(balls):
        if i == shot.target_ball_idx:
            continue
        p = np.array([ball.center_x, ball.center_y], dtype=float)
        d = dist(cue_final, p)
        min_dist = min(min_dist, d)

    safety = min_dist / (risk_radius * risk_factor)
    return clamp01(safety)


def score_scratch_safety(shot, table_layout, ball_r):
    if len(shot.cue_path) < 1:
        return 1.0

    pv_cfg = settings.module3_physics.scoring.position_value
    cue_final = np.array(shot.cue_path[-1], dtype=float)
    min_pocket_dist = 999999.0

    for pocket in table_layout.pockets:
        d = dist(cue_final, np.array(pocket, dtype=float))
        min_pocket_dist = min(min_pocket_dist, d)

    danger_radius = ball_r * pv_cfg.scratch_danger_factor * 4.0
    safety = min_pocket_dist / danger_radius
    return clamp01(safety)


def compute_position_value(shot, table_layout=None, balls=None):
    if table_layout is None:
        return 1.0

    pv_cfg = settings.module3_physics.scoring.position_value
    ball_r = float(balls[0].radius) if balls else 18.0

    collision_safety = score_collision_safety(shot, balls, ball_r)
    scratch_safety = score_scratch_safety(shot, table_layout, ball_r)

    score = (
            pv_cfg.w_collision_safety * collision_safety +
            pv_cfg.w_scratch_safety * scratch_safety
    )
    return clamp01(score)


# ============================================================
# DIFFICULTY PENALTY & FINAL SCORE
# ============================================================
def penalty_bank_shot(shot):
    return 1.0 if shot.shot_type == "bank" else 0.0


def penalty_long_shot(shot, max_path):
    return clamp01(shot.total_path_length / max_path)


def penalty_thin_cut(shot):
    max_angle = settings.module3_physics.physics.max_cut_angle_deg
    angle = min(abs(shot.cut_angle), max_angle)
    return clamp01(angle / max_angle)


def compute_difficulty_penalty(shot, table_layout=None):
    df_cfg = settings.module3_physics.scoring.difficulty_penalty

    if table_layout:
        diagonal = (table_layout.width ** 2 + table_layout.height ** 2) ** 0.5
        max_path = diagonal * 2.0
    else:
        max_path = settings.module3_physics.scoring.constants.default_max_path

    penalty = (
            df_cfg.w_bank * penalty_bank_shot(shot) +
            df_cfg.w_long_shot * penalty_long_shot(shot, max_path) +
            df_cfg.w_thin_cut * penalty_thin_cut(shot)
    )
    return clamp01(penalty)


def compute_shot_score(shot, table_layout=None, balls=None):
    w_cfg = settings.module3_physics.scoring.weights

    score = (
            w_cfg.pocket_probability * shot.pocket_probability +
            w_cfg.position_value * shot.position_value -
            w_cfg.difficulty_penalty * shot.difficulty_penalty
    )
    return clamp01(score)


# ============================================================
# BATCH SCORING & RANKING
# ============================================================
def score_all_shots(shots, table_layout=None, balls=None):
    for shot in shots:
        if shot.is_blocked:
            shot.pocket_probability = 0.0
            shot.position_value = 0.0
            shot.difficulty_penalty = 0.0
            shot.score = 0.0
            continue

        shot.pocket_probability = compute_pocket_probability(shot, table_layout, balls)
        shot.position_value = compute_position_value(shot, table_layout, balls)
        shot.difficulty_penalty = compute_difficulty_penalty(shot, table_layout)
        shot.score = compute_shot_score(shot, table_layout, balls)
    return shots


def get_top_shots(shots, top_n=5, table_layout=None, balls=None, min_score=0.0, deduplicate=True):
    if not shots:
        return []

    score_all_shots(shots, table_layout, balls)

    filtered = [
        s for s in shots
        if not s.is_blocked and s.score >= min_score
    ]

    if deduplicate:
        best_by_key = {}
        for shot in filtered:
            key = (shot.target_ball_idx, shot.pocket_idx)
            if key not in best_by_key or shot.score > best_by_key[key].score:
                best_by_key[key] = shot
        filtered = list(best_by_key.values())

    filtered.sort(key=lambda s: s.score, reverse=True)
    return filtered[:top_n]


def get_best_shot_per_ball(shots, table_layout=None, balls=None):
    score_all_shots(shots, table_layout, balls)

    best = {}
    for shot in shots:
        if shot.is_blocked:
            continue
        idx = shot.target_ball_idx
        if idx not in best or shot.score > best[idx].score:
            best[idx] = shot
    return best