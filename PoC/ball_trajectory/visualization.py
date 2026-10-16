import cv2
import numpy as np
from trajectory import ShotResult
from collision import compute_remaining_velocity
from config import settings


def _velocity_color(velocity: float):
    v_cfg = settings.module3_physics.visualization.velocity_tiers
    v = max(0.0, min(1.0, velocity))

    if v >= v_cfg.high_threshold:
        return tuple(v_cfg.high_color)
    elif v >= v_cfg.med_threshold:
        t = (v - v_cfg.med_threshold) / (v_cfg.high_threshold - v_cfg.med_threshold)
        g = int(v_cfg.low_color[1] + t * (v_cfg.high_color[1] - v_cfg.low_color[1]))
        r = int(v_cfg.high_color[2] - t * (v_cfg.high_color[2] - v_cfg.low_color[2]))
        b = int(v_cfg.high_color[0])  # Usually 0 for blue/red/yellow
        return (b, g, r)
    elif v >= v_cfg.low_threshold:
        t = (v - v_cfg.low_threshold) / (v_cfg.med_threshold - v_cfg.low_threshold)
        g = int(v_cfg.low_color[1] + t * (v_cfg.high_color[1] - v_cfg.low_color[1]))
        return (0, g, 220)
    else:
        return tuple(v_cfg.low_color)


def _velocity_bars(velocity: float) -> str:
    v_cfg = settings.module3_physics.visualization.velocity_tiers
    if velocity >= v_cfg.high_threshold:
        return "HI"
    elif velocity >= v_cfg.med_threshold:
        return "MD"
    else:
        return "LO"


def _pt(p):
    return (int(round(float(p[0]))), int(round(float(p[1]))))


def _perp(v):
    return np.array([-v[1], v[0]], dtype=float)


def _intersect_segments(p1, p2, p3, p4):
    """
    Find the intersection of the path segment (p1-p2) and the pocket gate segment (p3-p4).
    """
    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    x3, y3 = float(p3[0]), float(p3[1])
    x4, y4 = float(p4[0]), float(p4[1])

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0.0 <= t <= 1.0 and -0.5 <= u <= 1.5:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _draw_capsule_segment(img, p1, p2, radius, color, line_thickness=1, fill_alpha=0.0, draw_end_caps=True):
    p1, p2 = np.array(p1, dtype=float), np.array(p2, dtype=float)
    seg_vec = p2 - p1
    seg_len = np.linalg.norm(seg_vec)
    if seg_len < 1e-6: return

    along = seg_vec / seg_len
    perp = _perp(along)
    offset = perp * radius

    corners = np.array([p1 + offset, p2 + offset, p2 - offset, p1 - offset], dtype=np.float32)

    if fill_alpha > 0.0:
        overlay = img.copy()
        cv2.fillConvexPoly(overlay, corners.astype(np.int32), color)
        cv2.addWeighted(overlay, fill_alpha, img, 1.0 - fill_alpha, 0, img)

    cv2.line(img, _pt(p1 + offset), _pt(p2 + offset), color, line_thickness)
    cv2.line(img, _pt(p1 - offset), _pt(p2 - offset), color, line_thickness)

    if draw_end_caps:
        r = int(round(radius))
        if r < 1: return
        angle_deg = float(np.degrees(np.arctan2(along[1], along[0])))
        cv2.ellipse(img, _pt(p1), (r, r), angle_deg, 90, 270, color, line_thickness)
        cv2.ellipse(img, _pt(p2), (r, r), angle_deg, -90, 90, color, line_thickness)


def _draw_capsule_path(img, path_points, radius, color, line_thickness=1, fill_alpha=0.15, arrow_at_end=False):
    if len(path_points) < 2: return
    n_segs = len(path_points) - 1

    for i in range(n_segs):
        p1 = np.array(path_points[i], dtype=float)
        p2 = np.array(path_points[i + 1], dtype=float)
        draw_start_cap = (i == 0)
        draw_end_cap = (i == n_segs - 1)

        _draw_capsule_segment(img, p1, p2, radius, color, line_thickness, fill_alpha, False)

        r = int(round(radius))
        if r >= 1:
            seg_vec = p2 - p1
            seg_len = np.linalg.norm(seg_vec)
            if seg_len > 1e-6:
                angle_deg = float(np.degrees(np.arctan2(seg_vec[1], seg_vec[0])))
                if draw_start_cap:
                    cv2.ellipse(img, _pt(p1), (r, r), angle_deg, 90, 270, color, line_thickness)
                if draw_end_cap:
                    cv2.ellipse(img, _pt(p2), (r, r), angle_deg, -90, 90, color, line_thickness)

    if arrow_at_end and len(path_points) >= 2:
        cv2.arrowedLine(img, _pt(path_points[-2]), _pt(path_points[-1]), color, line_thickness, tipLength=0.15)


def _draw_dashed_line(img, p1, p2, color, thickness=1, dash_len=10, gap_len=6):
    p1, p2 = np.array(p1, dtype=float), np.array(p2, dtype=float)
    total = np.linalg.norm(p2 - p1)
    if total < 1: return
    direction = (p2 - p1) / total
    pos = 0.0
    drawing = True
    while pos < total:
        seg_end = min(pos + (dash_len if drawing else gap_len), total)
        if drawing:
            cv2.line(img, _pt(p1 + direction * pos), _pt(p1 + direction * seg_end), color, thickness)
        pos = seg_end
        drawing = not drawing


def _draw_ghost_ball(img, center, radius, color):
    cx, cy, r = int(center[0]), int(center[1]), int(radius)
    for i in range(20):
        if i % 2 == 0:
            a1, a2 = (2 * np.pi * i) / 20, (2 * np.pi * (i + 1)) / 20
            cv2.line(img, (int(cx + r * np.cos(a1)), int(cy + r * np.sin(a1))),
                     (int(cx + r * np.cos(a2)), int(cy + r * np.sin(a2))), color, 1)


def _draw_bank_point(img, bank_point, color, size=8):
    bx, by = int(bank_point[0]), int(bank_point[1])
    pts = np.array([[bx, by - size], [bx + size, by], [bx, by + size], [bx - size, by]], dtype=np.int32)
    cv2.fillPoly(img, [pts], color)
    cv2.polylines(img, [pts], True, (255, 255, 255), 1)


def _draw_bank_velocity_label(img, bank_point, velocity_at_bank: float):
    bx, by = int(bank_point[0]), int(bank_point[1])
    label = f"{int(velocity_at_bank * 100)}%"
    color = _velocity_color(velocity_at_bank)
    cv2.putText(img, label, (bx + 10, by - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, color, 1, cv2.LINE_AA)


def draw_single_shot(
        img,
        shot,
        ball_radius,
        rank=1,
        alpha=1.0,
        table_layout=None,
        overlay=None
):
    thickness = settings.module3_physics.visualization.styling.thickness_rest

    if alpha < 1.0:
        if overlay is None:
            overlay = img.copy()
        else:
            overlay[:] = img

        _draw_shot_on(
            overlay,
            shot,
            ball_radius,
            thickness,
            rank,
            table_layout
        )

        cv2.addWeighted(
            overlay,
            alpha,
            img,
            1.0 - alpha,
            0,
            img
        )

    else:
        _draw_shot_on(
            img,
            shot,
            ball_radius,
            thickness,
            rank,
            table_layout
        )


def _draw_shot_on(img, shot, ball_radius, thickness, rank, table_layout=None):
    colors_cfg = settings.module3_physics.visualization.colors
    style_cfg = settings.module3_physics.visualization.styling

    r = float(ball_radius)
    fill_a = style_cfg.fill_alpha_top1 if rank == 1 else style_cfg.fill_alpha_rest

    v = getattr(shot, "velocity_remaining", 1.0)
    target_color = _velocity_color(v)

    target_path = list(shot.target_path)

    if table_layout is not None and len(target_path) >= 2:
        pocket_id = getattr(shot, 'pocket_idx', None)
        if pocket_id is not None and pocket_id < 6:
            gate = table_layout.pocket_gates[pocket_id]

            new_path = []
            for i in range(len(target_path) - 1):
                p1 = target_path[i]
                p2 = target_path[i + 1]
                new_path.append(p1)

                intersect = _intersect_segments(p1, p2, gate[0], gate[1])
                if intersect is not None:
                    new_path.append(intersect)
                    break
            else:
                new_path.append(target_path[-1])

            target_path = new_path

    if len(shot.cue_path) >= 2:
        _draw_capsule_path(img, shot.cue_path, r, tuple(colors_cfg.cue_path), thickness, fill_a, False)
    if shot.ghost_pos is not None:
        _draw_ghost_ball(img, shot.ghost_pos, r, tuple(colors_cfg.ghost_ball))
    if len(target_path) >= 2:
        _draw_capsule_path(img, target_path, r, target_color, thickness, fill_a, False)

    if shot.bank_point is not None:
        _draw_bank_point(img, shot.bank_point, tuple(colors_cfg.bank_point))
        if len(shot.target_path) >= 2:
            v_at_bank = compute_remaining_velocity(
                path_segments=[(shot.target_path[0], shot.bank_point)],
                cushion_count=0,
            )
            _draw_bank_velocity_label(img, shot.bank_point, v_at_bank)

    if len(shot.cue_deflect_path) >= 2:
        _draw_dashed_line(img, shot.cue_deflect_path[0], shot.cue_deflect_path[-1], tuple(colors_cfg.cue_deflect), 1)

    px, py = int(shot.pocket_pos[0]), int(shot.pocket_pos[1])
    cv2.circle(img, (px, py), int(r * 0.8), tuple(colors_cfg.pocket_target), 2)

    if rank <= 3 and shot.cue_path:
        label_pos = _pt(np.array(shot.cue_path[0]) + np.array([-5, -12]))
        pocket_names = ["TL", "TM", "TR", "BL", "BM", "BR"]
        pocket_label = pocket_names[shot.pocket_idx] if shot.pocket_idx < 6 else "?"
        v_bar = _velocity_bars(v)
        cv2.putText(img, f"#{rank} {shot.shot_type[0].upper()} -> {pocket_label} {shot.score:.2f} [{v_bar}]",
                    label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, tuple(colors_cfg.score_text), 1, cv2.LINE_AA)


def draw_top_shots(
        img,
        top_shots,
        ball_radius,
        table_layout=None,
        overlay_buffer=None
):
    style_cfg = settings.module3_physics.visualization.styling

    if img is None:
        return None

    if table_layout is not None:
        _draw_pocket_markers(
            img,
            table_layout,
            ball_radius,
            top_shots
        )

    if not top_shots:
        h, w = img.shape[:2]
        cv2.putText(
            img,
            "No valid shots found",
            (w // 2 - 100, h // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 200),
            2,
            cv2.LINE_AA
        )
        return img

    for rank, shot in enumerate(reversed(top_shots), 1):
        actual_rank = len(top_shots) - rank + 1
        alpha = 1.0 if actual_rank == 1 else style_cfg.alpha_rest

        draw_single_shot(
            img,
            shot,
            ball_radius,
            rank=actual_rank,
            alpha=alpha,
            table_layout=table_layout,
            overlay=overlay_buffer
        )

    _draw_legend(img, len(top_shots))
    return img


def _draw_pocket_markers(img, table_layout, ball_radius, top_shots):
    target_pockets = {s.pocket_idx for s in top_shots}
    pocket_names = ["TL", "TM", "TR", "BL", "BM", "BR"]

    if hasattr(table_layout, 'pocket_gates'):
        for (g1, g2) in table_layout.pocket_gates:
            cv2.line(img, _pt(g1), _pt(g2), (0, 255, 255), 2)

    for i, pocket in enumerate(table_layout.pockets):
        px, py = int(pocket[0]), int(pocket[1])
        r = max(6, int(ball_radius * 0.6))
        color = (0, 0, 200) if i in target_pockets else (0, 160, 0)
        cv2.circle(img, (px, py), r, color, 1)
        cv2.putText(img, pocket_names[i], (px + r + 2, py + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)


def _draw_legend(
        img,
        num_shots,
):
    colors_cfg = settings.module3_physics.visualization.colors
    v_cfg = settings.module3_physics.visualization.velocity_tiers

    h, w = img.shape[:2]
    x0, y0 = w - 200, 15

    items = [
        (tuple(colors_cfg.cue_path), "Cue ball"),
        (tuple(v_cfg.high_color), "Target - high power"),
        ((0, 180, 220), "Target - med power"),  # Kept static because it is a gradient range
        (tuple(v_cfg.low_color), "Target - low power"),
        (tuple(colors_cfg.cue_deflect), "Deflect"),
        (tuple(colors_cfg.bank_point), "Bank pt"),
        ((0, 255, 255), "Pocket Gate"),
    ]

    overlay = img.copy()

    cv2.rectangle(
        overlay,
        (x0 - 5, y0 - 5),
        (w - 5, y0 + len(items) * 18 + 18),
        (30, 30, 30),
        -1
    )

    cv2.addWeighted(
        overlay,
        0.5,
        img,
        0.5,
        0,
        img
    )

    for i, (color, label) in enumerate(items):
        y = y0 + i * 18 + 12
        cv2.line(img, (x0, y), (x0 + 20, y), color, 2)
        cv2.putText(img, label, (x0 + 25, y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1)

    cv2.putText(
        img,
        f"Shots found: {num_shots}",
        (x0, y0 + len(items) * 18 + 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (200, 200, 200),
        1
    )