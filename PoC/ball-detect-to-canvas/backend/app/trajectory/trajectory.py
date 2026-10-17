"""
trajectory.py — Calculates ball trajectory: Direct Shot and Bank Shot (1 cushion).
Acts as the Orchestrator.
"""

import numpy as np
from .geometry import dist
from .collision import compute_collision, compute_remaining_velocity
from .pathfinder import generate_direct_paths, generate_bank_paths
from .trajectory_validator import is_path_blocked, is_cutting_cushion, trace_to_cushion
from .config import settings


# ─────────────────────────────────────────────────────────────
# ShotResult
# ─────────────────────────────────────────────────────────────
class ShotResult:
    def __init__(self, shot_type, target_ball_idx, pocket_idx, pocket_pos):
        self.shot_type = shot_type
        self.target_ball_idx = target_ball_idx
        self.pocket_idx = pocket_idx
        self.pocket_pos = np.array(pocket_pos, dtype=float)
        self.cue_path = []
        self.target_path = []
        self.cue_deflect_path = []
        self.ghost_pos = None
        self.contact_point = None
        self.cut_angle = 0.0
        self.bank_cushion = None
        self.bank_point = None

        self.score = 0.0
        self.pocket_probability = 0.0
        self.position_value = 0.0
        self.difficulty_penalty = 0.0

        self.is_blocked = False
        self.block_reason = ""
        self.total_path_length = 0.0
        self.velocity_remaining = 1.0

    def compute_total_length(self):
        self.total_path_length = sum(
            dist(p[i], p[i + 1])
            for p in [self.cue_path, self.target_path]
            for i in range(len(p) - 1)
        )
        return self.total_path_length

    def to_dict(self):
        def a2l(arr): return None if arr is None else [float(x) for x in arr]

        def p2l(path): return [[float(p[0]), float(p[1])] for p in path]

        return {
            "target_ball": self.target_ball_idx,
            "pocket": self.pocket_idx,
            "shot_type": self.shot_type,
            "score": self.score,
            "score_components": {
                "pocket_probability": self.pocket_probability,
                "position_value": self.position_value,
                "difficulty_penalty": self.difficulty_penalty
            },
            "cut_angle": self.cut_angle,
            "path_length": self.total_path_length,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.block_reason,
            "velocity_remaining": self.velocity_remaining,
            "cue_path": p2l(self.cue_path),
            "target_path": p2l(self.target_path),
            "cue_deflect_path": p2l(self.cue_deflect_path),
            "ghost_pos": a2l(self.ghost_pos),
            "bank_cushion": self.bank_cushion,
            "bank_point": a2l(self.bank_point),
        }


# ─────────────────────────────────────────────────────────────
# SHOT EVALUATION LOGIC
# ─────────────────────────────────────────────────────────────
def evaluate_direct_shot(cue_idx, target_idx, pocket_idx, balls, table_layout):
    val_cfg = settings.module3_physics.trajectory_validation

    cue_pos = np.array([balls[cue_idx].center_x, balls[cue_idx].center_y], dtype=float)
    target_pos = np.array([balls[target_idx].center_x, balls[target_idx].center_y], dtype=float)
    ball_r = float(balls[cue_idx].radius)
    pocket_pos = table_layout.pockets[pocket_idx]

    best_blocked = ShotResult("direct", target_idx, pocket_idx, pocket_pos)
    best_blocked.is_blocked, best_blocked.block_reason = True, "no_clear_path"

    candidates = generate_direct_paths(pocket_idx, table_layout, ball_r * val_cfg.direct_gate_margin_factor)
    for cand in candidates:
        shot = ShotResult("direct", target_idx, pocket_idx, pocket_pos)

        collision = compute_collision(cue_pos, target_pos, cand.aim_point, ball_r, table_layout)
        if not collision.is_valid:
            shot.is_blocked, shot.block_reason = True, "ghost_ball_invalid"
            best_blocked = shot;
            continue

        shot.ghost_pos, shot.cut_angle = collision.ghost_pos, collision.cut_angle

        # Validation Chain
        if is_path_blocked(cue_pos, shot.ghost_pos, balls, ball_r, (cue_idx, target_idx))[0]:
            shot.is_blocked, shot.block_reason = True, "cue_blocked"
            best_blocked = shot;
            continue
        if is_cutting_cushion(cue_pos, shot.ghost_pos, table_layout, ball_r)[0]:
            shot.is_blocked, shot.block_reason = True, "cue_cuts_cushion"
            best_blocked = shot;
            continue
        if is_path_blocked(target_pos, cand.aim_point, balls, ball_r, (cue_idx, target_idx))[0]:
            shot.is_blocked, shot.block_reason = True, "target_blocked"
            best_blocked = shot;
            continue
        if is_cutting_cushion(target_pos, cand.aim_point, table_layout, ball_r)[0]:
            shot.is_blocked, shot.block_reason = True, "target_cuts_cushion"
            best_blocked = shot;
            continue

        # Success!
        shot.velocity_remaining = compute_remaining_velocity([(target_pos, cand.aim_point)], cushion_count=0)
        shot.cue_path = [cue_pos, shot.ghost_pos]
        shot.target_path = [target_pos, cand.aim_point, pocket_pos]

        if collision.cue_deflect_dir is not None:
            shot.cue_deflect_path = [shot.ghost_pos,
                                     trace_to_cushion(shot.ghost_pos, collision.cue_deflect_dir, table_layout,
                                                      val_cfg.deflect_trace_direct)]

        shot.compute_total_length()
        return shot

    return best_blocked


def evaluate_bank_shot(cue_idx, target_idx, pocket_idx, cushion_name, balls, table_layout):
    val_cfg = settings.module3_physics.trajectory_validation
    phys_cfg = settings.module3_physics.physics

    cue_pos = np.array([balls[cue_idx].center_x, balls[cue_idx].center_y], dtype=float)
    target_pos = np.array([balls[target_idx].center_x, balls[target_idx].center_y], dtype=float)
    ball_r = float(balls[cue_idx].radius)
    pocket_pos = table_layout.pockets[pocket_idx]

    best_blocked = ShotResult("bank", target_idx, pocket_idx, pocket_pos)
    best_blocked.bank_cushion = cushion_name
    best_blocked.is_blocked, best_blocked.block_reason = True, "no_clear_bank"

    candidates = generate_bank_paths(target_pos, pocket_idx, cushion_name, table_layout, ball_r,
                                     phys_cfg.bank_offset_angle_deg)
    for cand in candidates:
        shot = ShotResult("bank", target_idx, pocket_idx, pocket_pos)
        shot.bank_cushion, shot.bank_point = cand.bank_cushion, cand.bank_point

        # Validate bank point isn't inside a pocket
        if any(dist(shot.bank_point, p_pos) < ball_r * val_cfg.bank_pocket_exclusion for p_pos in table_layout.pockets):
            continue

        collision = compute_collision(cue_pos, target_pos, shot.bank_point, ball_r, table_layout)
        if not collision.is_valid:
            shot.is_blocked, shot.block_reason = True, "bank_ghost_invalid"
            best_blocked = shot;
            continue

        shot.ghost_pos, shot.cut_angle = collision.ghost_pos, collision.cut_angle

        # Validation Chain
        if is_path_blocked(cue_pos, shot.ghost_pos, balls, ball_r, (cue_idx, target_idx))[0]:
            shot.is_blocked, shot.block_reason = True, "bank_cue_blocked"
            best_blocked = shot;
            continue
        if is_cutting_cushion(cue_pos, shot.ghost_pos, table_layout, ball_r)[0]:
            shot.is_blocked, shot.block_reason = True, "bank_cue_cuts"
            best_blocked = shot;
            continue
        if is_path_blocked(target_pos, shot.bank_point, balls, ball_r, (cue_idx, target_idx))[0]:
            shot.is_blocked, shot.block_reason = True, "bank_tgt_blocked"
            best_blocked = shot;
            continue
        if is_cutting_cushion(target_pos, shot.bank_point, table_layout, ball_r)[0]:
            shot.is_blocked, shot.block_reason = True, "bank_tgt_cuts"
            best_blocked = shot;
            continue
        if is_path_blocked(shot.bank_point, cand.aim_point, balls, ball_r, (cue_idx, target_idx))[0]:
            shot.is_blocked, shot.block_reason = True, "bank_to_pocket_blocked"
            best_blocked = shot;
            continue
        if is_cutting_cushion(shot.bank_point, cand.aim_point, table_layout, ball_r)[0]:
            shot.is_blocked, shot.block_reason = True, "bank_to_pocket_cuts"
            best_blocked = shot;
            continue

        v_remaining = compute_remaining_velocity(
            path_segments=[(target_pos, shot.bank_point), (shot.bank_point, cand.aim_point)], cushion_count=1
        )
        if v_remaining < phys_cfg.min_velocity:
            shot.is_blocked, shot.block_reason = True, "insufficient_velocity"
            best_blocked = shot;
            continue

        # Success!
        shot.velocity_remaining = v_remaining
        shot.cue_path = [cue_pos, shot.ghost_pos]
        shot.target_path = [target_pos, shot.bank_point, cand.aim_point, pocket_pos]

        if collision.cue_deflect_dir is not None:
            shot.cue_deflect_path = [shot.ghost_pos,
                                     trace_to_cushion(shot.ghost_pos, collision.cue_deflect_dir, table_layout,
                                                      val_cfg.deflect_trace_bank)]

        shot.compute_total_length()
        return shot

    return best_blocked


# ─────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────
def find_all_shots(balls, table_layout):
    cue_idx = next((i for i, b in enumerate(balls) if b.class_name == "cue_ball"), None)
    if cue_idx is None:
        return []

    valid_shots = []

    for target_idx in range(len(balls)):
        if target_idx == cue_idx:
            continue

        # 1. Direct Shots
        for pocket_idx in range(6):
            shot = evaluate_direct_shot(cue_idx, target_idx, pocket_idx, balls, table_layout)
            valid_shots.append(shot)

        # 2. Bank Shots (1 cushion)
        for cushion_name in ["top", "right", "bottom", "left"]:
            for pocket_idx in range(6):
                shot = evaluate_bank_shot(cue_idx, target_idx, pocket_idx, cushion_name, balls, table_layout)
                if shot:
                    valid_shots.append(shot)

    return valid_shots