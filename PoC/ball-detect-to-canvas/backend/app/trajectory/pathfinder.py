import numpy as np
from dataclasses import dataclass
from typing import Optional
from .geometry import mirror_point, line_intersection, normalize


@dataclass
class PathCandidate:
    shot_type: str
    aim_point: np.ndarray
    bank_cushion: Optional[str] = None
    bank_point: Optional[np.ndarray] = None


def get_gate_alphas(gate_p1, gate_p2, safe_margin):
    """Calculate the interpolation coefficients alpha on the pocket gate segment."""
    gate_vec = np.array(gate_p2) - np.array(gate_p1)
    gate_len = np.linalg.norm(gate_vec)

    if gate_len == 0:
        return []
    if gate_len <= 2 * safe_margin:
        return [0.5]

    margin_alpha = safe_margin / gate_len
    step = (0.5 - margin_alpha) / 2.0
    return [0.5, 0.5 - step, 0.5 + step, margin_alpha, 1.0 - margin_alpha]


def generate_direct_paths(pocket_idx, table_layout, safe_margin) -> list[PathCandidate]:
    """Generate direct aim points to the pocket."""
    gate_p1, gate_p2 = table_layout.pocket_gates[pocket_idx]
    gate_vec = np.array(gate_p2) - np.array(gate_p1)
    alphas = get_gate_alphas(gate_p1, gate_p2, safe_margin)

    return [PathCandidate("direct", np.array(gate_p1) + a * gate_vec) for a in alphas]


def get_cushion_normal(table_layout, cushion_name):
    for name, n in table_layout.cushion_normals:
        if name == cushion_name:
            return n
    return None


_ADJACENT_CUSHIONS = {
    0: ("top", "left"), 1: ("top",), 2: ("top", "right"),
    3: ("bottom", "left"), 4: ("bottom",), 5: ("bottom", "right"),
}


def _find_offset_bank_point(target_pos, aim_point, eff_p1, eff_p2,
                             c_normal_unit, tang, offset_deg):
    """
    Calculate the bank_point with real-world reflection angle compensation using O(1) operations.

    Physics: In real billiards, the ball bounces off at a narrower angle than the incoming angle (angle_out < angle_in)
    due to forward roll and cushion friction. To compensate, it's necessary to aim with a larger incoming angle
    (α = β + offset) so that after the narrow bounce, the ball still goes in the correct pocket direction.

    O(1) Algorithm — no loops or searching, purely vector + trigonometry:
      1. At the ideal bank_point (mirror), calculate the angle β of the outgoing ray with the cushion normal.
      2. Required incoming angle: α = β + offset_deg.
      3. Construct a new incoming ray from target_pos with angle α → intersection with cushion = bank_point_adjusted.
    """
    # Step 1: ideal bank_point (perfect mirror reflection)
    mirror_aim = mirror_point(aim_point, eff_p1, eff_p2)
    bank_pt_ideal, t_ideal, s_ideal = line_intersection(target_pos, mirror_aim, eff_p1, eff_p2)

    if bank_pt_ideal is None or t_ideal < 0 or not (0.0 <= s_ideal <= 1.0):
        return None, None, None

    if abs(offset_deg) < 1e-6:
        return bank_pt_ideal, t_ideal, s_ideal

    # Step 2: angle β — angle between the outgoing ray (→ aim_point) and the cushion normal at the ideal bank_point
    d_out = normalize(np.array(aim_point, dtype=float) - bank_pt_ideal)
    cos_beta = float(np.dot(d_out, c_normal_unit))

    # d_out must point inwards into the table (dot with inward normal > 0)
    if cos_beta <= 1e-6:
        return bank_pt_ideal, t_ideal, s_ideal  # Fallback: aim_point is behind the cushion

    beta_rad = np.arccos(np.clip(cos_beta, -1.0, 1.0))

    # Step 3: required incoming angle α = β + offset (larger to compensate for the narrow reflection)
    alpha_rad = beta_rad + np.radians(offset_deg)

    if alpha_rad >= np.pi / 2.0 - 1e-6:
        # Incoming angle near 90° — ball almost runs along the cushion, not feasible → fallback
        return bank_pt_ideal, t_ideal, s_ideal

    # Step 4: tangent direction — determine which side of the cushion d_out "leans" towards
    tang_sign = 1.0 if np.dot(d_out, tang) >= 0 else -1.0

    # Step 5: construct the new incoming ray direction with angle α from the normal
    # Incoming ray pointing INTO the cushion (opposite to normal): d_in = -cos(α)*n + sin(α)*tang_sign*t
    d_in_new = -np.cos(alpha_rad) * c_normal_unit + np.sin(alpha_rad) * tang_sign * tang
    d_in_new = normalize(d_in_new)

    # Step 6: trace from target_pos along d_in_new → intersection with the cushion segment
    far_pt = np.array(target_pos, dtype=float) + d_in_new * 1e6
    bank_pt_adj, t_adj, s_adj = line_intersection(target_pos, far_pt, eff_p1, eff_p2)

    if bank_pt_adj is not None and t_adj >= 0 and (0.0 <= s_adj <= 1.0):
        return bank_pt_adj, t_adj, s_adj

    # Fallback if the compensated point lies outside the cushion segment
    return bank_pt_ideal, t_ideal, s_ideal


def generate_bank_paths(target_pos, pocket_idx, cushion_name, table_layout, ball_r,
                        bank_offset_deg: float = 0.0) -> list[PathCandidate]:
    """
    Generate 1-cushion (Bank) aim points to the pocket.

    Args:
        bank_offset_deg: Real-world reflection compensation angle (degrees). Positive value (+) = aim
                         with a larger incoming angle to compensate for the phenomenon where the ball
                         bounces off narrower in reality (angle_out < angle_in due to forward roll + cushion friction).
                         Set to 0 to use pure mirror reflection.
    """
    if cushion_name in _ADJACENT_CUSHIONS[pocket_idx]:
        return []

    cushion_seg = next(((p1, p2) for n, p1, p2 in table_layout.cushions if n == cushion_name), None)
    c_normal = get_cushion_normal(table_layout, cushion_name)

    if not cushion_seg or c_normal is None:
        return []

    # Effective cushion impact point (including ball radius)
    eff_p1 = np.array(cushion_seg[0]) + c_normal * ball_r
    eff_p2 = np.array(cushion_seg[1]) + c_normal * ball_r

    c_normal_unit = normalize(np.array(c_normal, dtype=float))
    tang = normalize(eff_p2 - eff_p1)

    gate_p1, gate_p2 = table_layout.pocket_gates[pocket_idx]
    alphas = get_gate_alphas(gate_p1, gate_p2, ball_r * 1.3)
    gate_vec = np.array(gate_p2) - np.array(gate_p1)

    paths = []
    for alpha in alphas:
        aim_point = np.array(gate_p1) + alpha * gate_vec

        bank_point_raw, t, s = _find_offset_bank_point(
            target_pos, aim_point, eff_p1, eff_p2,
            c_normal_unit, tang, bank_offset_deg
        )

        if bank_point_raw is not None:
            paths.append(PathCandidate("bank", aim_point, cushion_name, bank_point_raw))

    return paths