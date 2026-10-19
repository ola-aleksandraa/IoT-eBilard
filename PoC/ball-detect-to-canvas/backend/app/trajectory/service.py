"""Glue between the detection API (normalised 0-1 table coordinates) and the shot-planning engine (pixels)."""
from __future__ import annotations

import numpy as np
from statistics import median
from typing import Iterable

from .geometry import angle_deg, length, normalize, point_to_segment_distance
from .geometry_builder import build_static_geometry
from .shot_scoring import get_top_shots, score_all_shots
from .table_types import TrackedBall
from .trajectory import find_all_shots

# The engine's constants (friction, margins, ...) are tuned in pixels for a table about this wide.
ENGINE_WIDTH = 1000.0
MAX_CUT_DEG = 85.0
MIN_REMAINING_VELOCITY = 0.05

# Real-motion simulation constants (engine pixels: the table is W px wide).
SIM_FRICTION = 420.0        # uniform rolling deceleration, px/s²
SIM_FULL_SPEED = 1500.0     # cue-ball speed at power = 1, px/s
SIM_MIN_SPEED = 500.0       # cue-ball speed at power = 0, px/s
SIM_STOP_SPEED = 15.0       # below this the ball is considered at rest
SIM_E_BALL = 0.94           # ball-to-ball restitution
SIM_E_CUSHION = 0.72        # cushion restitution
SIM_CAPTURE = 1.5           # pot distance from a pocket centre, in ball radii
SIM_MOUTH = 2.6             # cushion reflection is skipped this close to a pocket
SIM_DT = 1.0 / 240.0        # integration step, seconds
SIM_SAMPLE_EVERY = 6        # keep one pose every N steps (→ 25 ms pose spacing)
SIM_MAX_SECONDS = 10.0


def plan_shots(balls: Iterable, table_ratio: float, top_n: int = 5,
               include_bank: bool = True, include_blocked: bool = False) -> dict:
    """balls: objects with id, kind, x, y, radius (x/y in 0-1 of table width/height, radius in 0-1 of height)."""
    balls = list(balls)
    W = ENGINE_WIDTH
    H = W / table_ratio
    engine_balls = [
        TrackedBall(track_id=b.id, class_name="cue_ball" if b.kind == "cue" else b.kind,
                    center_x=b.x * W, center_y=b.y * H, radius=b.radius * H)
        for b in balls
    ]
    cue = [b for b in engine_balls if b.class_name == "cue_ball"]
    if len(cue) != 1:
        return {"status": "no_cue_ball" if not cue else "multiple_cue_balls",
                "cue_ball_id": None, "shots": [], "blocked": []}
    if len(engine_balls) < 2:
        return {"status": "no_targets", "cue_ball_id": cue[0].track_id, "shots": [], "blocked": []}

    geometry = build_static_geometry([[0, 0], [W, 0], [W, H], [0, H]],
                                     ball_radius=median(b.radius for b in engine_balls))
    all_shots = find_all_shots(engine_balls, geometry)
    if not include_bank:
        all_shots = [s for s in all_shots if s.shot_type == "direct" or s.is_blocked]
    score_all_shots(all_shots, geometry, engine_balls)
    top = get_top_shots(shots=all_shots, top_n=top_n, table_layout=geometry, balls=engine_balls,
                        min_score=0.0, deduplicate=True)
    blocked = [s for s in all_shots if s.is_blocked] if include_blocked else []

    return {"status": "ok", "cue_ball_id": cue[0].track_id,
            "shots": [_serialise(s, engine_balls, W, H) for s in top],
            "blocked": [_serialise(s, engine_balls, W, H) for s in blocked[:20]]}


def _serialise(shot, engine_balls, W, H) -> dict:
    data = shot.to_dict()
    norm = lambda p: None if p is None else [p[0] / W, p[1] / H]  # noqa: E731
    for key in ("cue_path", "target_path", "cue_deflect_path"):
        data[key] = [norm(p) for p in data[key]]
    data["ghost_pos"] = norm(data["ghost_pos"])
    data["bank_point"] = norm(data["bank_point"])
    data["target_ball_id"] = engine_balls[data["target_ball"]].track_id
    return data


def _engine_balls(balls, table_ratio: float) -> list[TrackedBall]:
    W = ENGINE_WIDTH
    H = W / table_ratio
    return [TrackedBall(track_id=b.id, class_name="cue_ball" if b.kind == "cue" else b.kind,
                        center_x=b.x * W, center_y=b.y * H, radius=b.radius * H)
            for b in balls]


def predict_shot(balls, table_ratio: float, aim: tuple[float, float]) -> dict:
    """Predict the outcome of aiming the cue ball at `aim` (0-1 table coordinates).

    Same coordinate convention as plan_shots, but for one given aim direction:
    which ball is hit first, ghost-ball position, cut angle, the best straight
    pocket for the hit ball, whether the shot is makeable, and drawing paths.
    """
    balls = list(balls)
    W = ENGINE_WIDTH
    H = W / table_ratio
    engine_balls = _engine_balls(balls, table_ratio)
    cue = [b for b in engine_balls if b.class_name == "cue_ball"]
    if len(cue) != 1:
        return {"status": "no_cue_ball" if not cue else "multiple_cue_balls",
                "cue_ball_id": None, "first_ball_id": None}
    if len(engine_balls) < 2:
        return {"status": "no_targets", "cue_ball_id": cue[0].track_id, "first_ball_id": None}

    cue_idx = engine_balls.index(cue[0])
    cue_pos = np.array([cue[0].center_x, cue[0].center_y])
    R = float(median(b.radius for b in engine_balls))

    aim_point = np.array([aim[0] * W, aim[1] * H])
    direction = aim_point - cue_pos
    if length(direction) < 2 * R:
        return {"status": "invalid_aim", "cue_ball_id": cue[0].track_id, "first_ball_id": None}
    dn = normalize(direction)

    geometry = build_static_geometry([[0, 0], [W, 0], [W, H], [0, H]], ball_radius=R)

    # ── First ball lying on the aim ray ─────────────────────────
    first: tuple[float, int] | None = None
    for index, ball in enumerate(engine_balls):
        if index == cue_idx:
            continue
        rel = np.array([ball.center_x, ball.center_y]) - cue_pos
        along = float(np.dot(rel, dn))
        if along <= 2 * R:
            continue  # behind the cue ball or already touching it
        perpendicular = float(length(rel - dn * along))
        if perpendicular >= 2 * R:
            continue
        # Cue-ball-centre distance at first contact (centres are then 2R apart).
        contact_t = along - float(np.sqrt(max(0.0, (2 * R) ** 2 - perpendicular ** 2)))
        if first is None or contact_t < first[0]:
            first = (contact_t, index)

    if first is None:  # pure miss: draw the aim line to the table edge
        to_x = ((W - cue_pos[0]) if dn[0] > 0 else (0 - cue_pos[0])) / dn[0] if dn[0] else float(np.inf)
        to_y = ((H - cue_pos[1]) if dn[1] > 0 else (0 - cue_pos[1])) / dn[1] if dn[1] else float(np.inf)
        aim_line = cue_pos + dn * min(to_x, to_y)
        return {"status": "ok", "cue_ball_id": cue[0].track_id, "first_ball_id": None,
                "ghost_pos": None, "cut_angle": None, "pocket": None, "makeable": False,
                "blocked_reason": None, "velocity_remaining": 0.0, "score": 0.0,
                "cue_path": [[cue_pos[0] / W, cue_pos[1] / H], [aim_line[0] / W, aim_line[1] / H]],
                "target_path": [], "cue_deflect_path": [], "bank_point": None}

    contact_t, target_idx = first
    target = engine_balls[target_idx]
    target_pos = np.array([target.center_x, target.center_y])
    ghost = cue_pos + dn * contact_t
    contact_dir = normalize(target_pos - ghost)

    # ── Best straight pocket for the hit ball ───────────────────
    # Prefer an unblocked pocket; within the same class take the smallest |cut|.
    best_pocket, best_cut, blocked_reason, to_pocket = None, None, "No pocket within the cut-angle limit.", None
    for pocket_idx, pocket in enumerate(geometry.pockets):
        candidate = pocket - target_pos
        if length(candidate) < 1e-9:
            continue
        cut = float(angle_deg(contact_dir, normalize(candidate)))
        blockers = [b for i, b in enumerate(engine_balls)
                    if i not in (cue_idx, target_idx)
                    and point_to_segment_distance((b.center_x, b.center_y),
                                                  tuple(target_pos), tuple(pocket)) < 2 * R]
        is_free, is_better = not blockers, True
        if best_cut is not None:
            was_free, pocket_taken = blocked_reason is None, best_pocket
            is_better = (is_free and not was_free) or (is_free == was_free and abs(cut) < abs(best_cut))
        if not is_better:
            continue
        best_cut, best_pocket, to_pocket = cut, pocket_idx, candidate
        blocked_reason = None if is_free else f"Target path blocked by ball {blockers[0].track_id}."

    cut = 0.0 if best_cut is None else best_cut
    velocity_remaining = float(np.cos(np.deg2rad(abs(cut))) ** 2)
    makeable = best_pocket is not None and abs(cut) <= MAX_CUT_DEG \
        and velocity_remaining >= MIN_REMAINING_VELOCITY and blocked_reason is None

    # ── Visualisation paths ──────────────────────────────────────
    cue_path = [[cue_pos[0] / W, cue_pos[1] / H], [ghost[0] / W, ghost[1] / H]]
    target_path = []
    if best_pocket is not None:
        pocket_point = geometry.pockets[best_pocket]
        target_path = [[target_pos[0] / W, target_pos[1] / H], [pocket_point[0] / W, pocket_point[1] / H]]
    deflect_path = []
    sideways = dn - contact_dir * float(np.dot(dn, contact_dir))
    if length(sideways) > 1e-6:
        sidestep = 0.15 * float(np.sin(np.deg2rad(abs(cut))))
        sideways = normalize(sideways)
        deflect_path = [[ghost[0] / W, ghost[1] / H],
                        [(ghost[0] + sideways[0] * sidestep * W) / W,
                         (ghost[1] + sideways[1] * sidestep * W) / H]]

    path_distance = contact_t + (float(length(to_pocket)) if to_pocket is not None else 0.0)
    cut_share = abs(cut) / MAX_CUT_DEG
    score = 0.0 if not makeable else float(np.clip(0.5 * (1 - cut_share) + 0.3 * velocity_remaining
                                                   + 0.2 * (1 - min(path_distance / (2.5 * W), 1.0)), 0.0, 1.0))

    return {"status": "ok", "cue_ball_id": cue[0].track_id, "first_ball_id": target.track_id,
            "ghost_pos": [ghost[0] / W, ghost[1] / H], "cut_angle": cut, "pocket": best_pocket,
            "makeable": bool(makeable), "blocked_reason": blocked_reason,
            "velocity_remaining": velocity_remaining, "score": score,
            "cue_path": cue_path, "target_path": target_path,
            "cue_deflect_path": deflect_path, "bank_point": None}


def simulate_motion(balls, table_ratio: float, aim: tuple[float, float], power: float = 0.6) -> dict:
    """Real-motion prediction: roll the shot out with 2-D physics.

    The cue ball leaves toward `aim` at a speed that rises with `power` (0-1; the
    frontend derives power from the aiming drag distance). Balls collide
    elastically, cushions absorb energy, everything stops under rolling friction,
    and any ball entering a pocket mouth drops. Returns per-ball position paths
    sampled every `dt` seconds (index = time / dt), the final resting layout and
    the event timeline (contacts, cushion hits, pots).
    Same coordinates as plan_shots: 0-1 table units in, 0-1 paths out; internally
    the simulation runs in plain engine-pixel floats for speed.
    """
    import math

    balls = list(balls)
    W = ENGINE_WIDTH
    H = W / table_ratio
    engine_balls = _engine_balls(balls, table_ratio)
    cue = [b for b in engine_balls if b.class_name == "cue_ball"]
    if len(cue) != 1:
        return {"status": "no_cue_ball" if not cue else "multiple_cue_balls",
                "cue_ball_id": None, "first_ball_id": None}
    if len(engine_balls) < 2:
        return {"status": "no_targets", "cue_ball_id": cue[0].track_id, "first_ball_id": None}

    cue_idx = engine_balls.index(cue[0])
    cue_id = cue[0].track_id
    R = float(median(b.radius for b in engine_balls))

    cue_pos = np.array([cue[0].center_x, cue[0].center_y], dtype=float)
    aim_point = np.array([aim[0] * W, aim[1] * H], dtype=float)
    direction = aim_point - cue_pos
    if length(direction) < 2 * R:
        return {"status": "invalid_aim", "cue_ball_id": cue_id, "first_ball_id": None}
    dn = normalize(direction)
    dvn_x, dvn_y = float(dn[0]), float(dn[1])

    geometry = build_static_geometry([[0, 0], [W, 0], [W, H], [0, H]], ball_radius=R)
    pocket_centers = [[float(p[0]), float(p[1])] for p in geometry.pockets]

    power = min(1.0, max(0.0, float(power)))
    speed = SIM_MIN_SPEED + (SIM_FULL_SPEED - SIM_MIN_SPEED) * power

    # Plain-float state for speed: positions / velocities as [x, y] lists.
    count = len(engine_balls)
    positions = [[ball.center_x, ball.center_y] for ball in engine_balls]
    velocities = [[0.0, 0.0] for _ in range(count)]
    velocities[cue_idx] = [dvn_x * speed, dvn_y * speed]
    radii = [float(ball.radius) for ball in engine_balls]
    paths: list[list[list[float]]] = [[[ball.center_x / W, ball.center_y / H]] for ball in engine_balls]
    potted_t: list[float | None] = [None] * count

    # Detection noise can leave balls touching or slightly overlapped; nudge them apart.
    for _ in range(4):
        for a in range(count):
            for b in range(a + 1, count):
                dx = positions[b][0] - positions[a][0]
                dy = positions[b][1] - positions[a][1]
                apart = math.hypot(dx, dy)
                wanted = radii[a] + radii[b]
                if 0 < apart < wanted:
                    push = (wanted - apart) / 2.0 / apart
                    positions[a][0] -= dx * push
                    positions[a][1] -= dy * push
                    positions[b][0] += dx * push
                    positions[b][1] += dy * push

    events: list[dict] = []

    def pot(ball_idx: int, pocket_idx: int, t: float):
        potted_t[ball_idx] = round(t, 4)
        pocket = pocket_centers[pocket_idx]
        positions[ball_idx] = [pocket[0], pocket[1]]
        velocities[ball_idx] = [0.0, 0.0]
        events.append({"t": round(t, 4), "type": "pot",
                       "ball": engine_balls[ball_idx].track_id, "pocket": pocket_idx,
                       "x": pocket[0] / W, "y": pocket[1] / H})

    last_contact: dict[tuple[int, int], float] = {}
    last_cushion: dict[int, float] = {}
    mouth = SIM_MOUTH * R
    capture = SIM_CAPTURE * R
    impulse_share = (1.0 + SIM_E_BALL) / 2.0
    stop_sq = SIM_STOP_SPEED * SIM_STOP_SPEED
    max_steps = int(SIM_MAX_SECONDS / SIM_DT)
    steps = 0

    while steps < max_steps:
        t = steps * SIM_DT
        moving = False
        for idx in range(count):
            if potted_t[idx] is None:
                vx, vy = velocities[idx]
                if vx * vx + vy * vy > stop_sq:
                    moving = True
                    break
        if not moving and steps > SIM_SAMPLE_EVERY:
            break
        # ── friction + translation ──
        for idx in range(count):
            if potted_t[idx] is not None:
                continue
            vx, vy = velocities[idx]
            current = math.hypot(vx, vy)
            if current > 0:
                slowed = current - SIM_FRICTION * SIM_DT
                factor = (slowed / current) if slowed > SIM_STOP_SPEED else 0.0
                vx *= factor
                vy *= factor
                velocities[idx] = [vx, vy]
            positions[idx][0] += vx * SIM_DT
            positions[idx][1] += vy * SIM_DT
        # ── ball-to-ball collisions ──
        for a in range(count):
            if potted_t[a] is not None:
                continue
            for b in range(a + 1, count):
                if potted_t[b] is not None:
                    continue
                dx = positions[b][0] - positions[a][0]
                dy = positions[b][1] - positions[a][1]
                wanted = radii[a] + radii[b]
                d2 = dx * dx + dy * dy
                if d2 <= 1e-15 or d2 >= wanted * wanted:
                    continue
                d = math.sqrt(d2)
                nx, ny = dx / d, dy / d
                overlap = (wanted - d) / 2.0
                positions[a][0] -= nx * overlap
                positions[a][1] -= ny * overlap
                positions[b][0] += nx * overlap
                positions[b][1] += ny * overlap
                approaching = (velocities[a][0] - velocities[b][0]) * nx \
                    + (velocities[a][1] - velocities[b][1]) * ny
                if approaching <= 1e-9:
                    continue  # already separating; just remove the overlap
                j = impulse_share * approaching
                velocities[a][0] -= nx * j
                velocities[a][1] -= ny * j
                velocities[b][0] += nx * j
                velocities[b][1] += ny * j
                key = (a, b)
                if t - last_contact.get(key, -1.0) < 0.15:
                    continue
                last_contact[key] = t
                event = {"t": round(t, 4), "type": "contact",
                         "x": (positions[a][0] + positions[b][0]) / (2.0 * W),
                         "y": (positions[a][1] + positions[b][1]) / (2.0 * H)}
                if a == cue_idx or b == cue_idx:
                    other_idx = b if a == cue_idx else a
                    cue_vx, cue_vy = velocities[cue_idx]
                    cue_dir_x, cue_dir_y = (dvn_x, dvn_y)
                    cue_speed = math.hypot(cue_vx, cue_vy)
                    if cue_speed > 1e-9:
                        cue_dir_x, cue_dir_y = cue_vx / cue_speed, cue_vy / cue_speed
                    cdx = positions[other_idx][0] - positions[cue_idx][0]
                    cdy = positions[other_idx][1] - positions[cue_idx][1]
                    clen = math.hypot(cdx, cdy) or 1.0
                    dot_p = max(-1.0, min(1.0, cue_dir_x * cdx / clen + cue_dir_y * cdy / clen))
                    event.update({"ball": engine_balls[other_idx].track_id,
                                  "with": engine_balls[cue_idx].track_id,
                                  "cut_angle": math.degrees(math.acos(dot_p))})
                else:
                    event.update({"ball": engine_balls[a].track_id, "with": engine_balls[b].track_id})
                events.append(event)
        # ── cushions and pockets ──
        for idx in range(count):
            if potted_t[idx] is not None:
                continue
            px, py = positions[idx]
            vx, vy = velocities[idx]
            r = radii[idx]
            in_mouth = False
            for pocket in pocket_centers:
                if math.hypot(px - pocket[0], py - pocket[1]) < mouth:
                    in_mouth = True
                    break
            if in_mouth:
                for pocket_idx, pocket in enumerate(pocket_centers):
                    if math.hypot(px - pocket[0], py - pocket[1]) < capture \
                            and vx * (pocket[0] - px) + vy * (pocket[1] - py) > 0:
                        pot(idx, pocket_idx, t)
                        break
            else:
                bounced = False
                if px < r:
                    positions[idx][0] = r
                    if vx < 0:
                        velocities[idx][0] = -vx * SIM_E_CUSHION
                        bounced = True
                elif px > W - r:
                    positions[idx][0] = W - r
                    if vx > 0:
                        velocities[idx][0] = -vx * SIM_E_CUSHION
                        bounced = True
                if py < r:
                    positions[idx][1] = r
                    if vy < 0:
                        velocities[idx][1] = -vy * SIM_E_CUSHION
                        bounced = True
                elif py > H - r:
                    positions[idx][1] = H - r
                    if vy > 0:
                        velocities[idx][1] = -vy * SIM_E_CUSHION
                        bounced = True
                if bounced and t - last_cushion.get(idx, -1.0) > 0.1:
                    last_cushion[idx] = t
                    events.append({"t": round(t, 4), "type": "cushion",
                                   "ball": engine_balls[idx].track_id,
                                   "x": positions[idx][0] / W, "y": positions[idx][1] / H})
            if potted_t[idx] is None and (px < -3 * R or px > W + 3 * R
                                          or py < -3 * R or py > H + 3 * R):
                nearest, best_d = 0, float("inf")
                for pocket_idx, pocket in enumerate(pocket_centers):
                    dd = math.hypot(px - pocket[0], py - pocket[1])
                    if dd < best_d:
                        best_d, nearest = dd, pocket_idx
                pot(idx, nearest, t)
        steps += 1
        if steps % SIM_SAMPLE_EVERY == 0:
            for idx in range(count):
                if potted_t[idx] is None:
                    paths[idx].append([positions[idx][0] / W, positions[idx][1] / H])

    cue_contact = next((e for e in events if e["type"] == "contact" and e.get("with") == cue_id), None)
    return {"status": "ok", "cue_ball_id": cue_id,
            "first_ball_id": cue_contact["ball"] if cue_contact else None,
            "ghost_pos": [cue_contact["x"], cue_contact["y"]] if cue_contact else None,
            "cut_angle": cue_contact["cut_angle"] if cue_contact else None,
            "power": power, "duration": round(steps * SIM_DT, 4),
            "dt": SIM_SAMPLE_EVERY * SIM_DT,
            "balls": [{"id": engine_balls[idx].track_id, "path": paths[idx],
                       "potted_t": potted_t[idx]} for idx in range(count)],
            "events": events,
            "potted": [engine_balls[idx].track_id for idx in range(count)
                       if potted_t[idx] is not None]}
