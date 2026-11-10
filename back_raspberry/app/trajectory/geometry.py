from __future__ import annotations

import numpy as np


def vec(p1, p2):
    return np.array(p2, dtype=float) - np.array(p1, dtype=float)


def normalize(v):
    v = np.array(v, dtype=float)
    length = np.linalg.norm(v)
    return np.zeros(2) if length < 1e-9 else v / length


def dot(v1, v2):
    return float(np.dot(v1, v2))


def length(v):
    return float(np.linalg.norm(v))


def dist(p1, p2):
    return float(np.linalg.norm(np.array(p2, dtype=float) - np.array(p1, dtype=float)))


def perpendicular_ccw(v):
    v = np.array(v, dtype=float)
    return np.array([-v[1], v[0]])


def perpendicular_cw(v):
    v = np.array(v, dtype=float)
    return np.array([v[1], -v[0]])


def angle_deg(v1, v2):
    cos_a = np.clip(dot(normalize(v1), normalize(v2)), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_a)))


def reflect_vector(v, normal):
    n = normalize(normal)
    v = np.array(v, dtype=float)
    return v - 2 * dot(v, n) * n


def mirror_point(point, line_p1, line_p2):
    p, a, b = np.array(point, dtype=float), np.array(line_p1, dtype=float), np.array(line_p2, dtype=float)
    ab, ap = b - a, p - a
    t = dot(ap, ab) / dot(ab, ab)
    foot = a + t * ab
    return 2 * foot - p


def line_intersection(p1, p2, p3, p4):
    d1 = np.array(p2, dtype=float) - np.array(p1, dtype=float)
    d2 = np.array(p4, dtype=float) - np.array(p3, dtype=float)
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < 1e-9: return None, None, None

    diff = np.array(p3, dtype=float) - np.array(p1, dtype=float)
    t = (diff[0] * d2[1] - diff[1] * d2[0]) / cross
    s = (diff[0] * d1[1] - diff[1] * d1[0]) / cross
    return np.array(p1, dtype=float) + t * d1, t, s


def segment_intersection(p1, p2, p3, p4):
    point, t, s = line_intersection(p1, p2, p3, p4)
    if point is None: return None
    eps = 1e-9
    if -eps <= t <= 1 + eps and -eps <= s <= 1 + eps: return point
    return None


def ray_segment_intersection(ray_origin, ray_dir, seg_p1, seg_p2):
    far = np.array(ray_origin, dtype=float) + np.array(ray_dir, dtype=float) * 1e6
    point, t, s = line_intersection(ray_origin, far, seg_p1, seg_p2)
    if point is None: return None, None
    eps = 1e-9
    if t >= -eps and -eps <= s <= 1 + eps: return point, t
    return None, None


def point_to_segment_distance(point, seg_p1, seg_p2):
    p, a, b = np.array(point, dtype=float), np.array(seg_p1, dtype=float), np.array(seg_p2, dtype=float)
    ab = b - a
    ab_len_sq = dot(ab, ab)
    if ab_len_sq < 1e-9: return dist(p, a)
    t = np.clip(dot(p - a, ab) / ab_len_sq, 0.0, 1.0)
    foot = a + t * ab
    return dist(p, foot)


def segment_to_segment_distance(p1, p2, p3, p4):
    if segment_intersection(p1, p2, p3, p4) is not None: return 0.0
    return min(point_to_segment_distance(p1, p3, p4),
               point_to_segment_distance(p2, p3, p4),
               point_to_segment_distance(p3, p1, p2),
               point_to_segment_distance(p4, p1, p2))


def ball_blocks_segment(ball_center, ball_radius, seg_p1, seg_p2, margin=0.0):
    return point_to_segment_distance(ball_center, seg_p1, seg_p2) < (ball_radius + margin)


def capsule_passes_gate(path_start, path_end, gate_p1, gate_p2, ball_radius):
    point, t, s = line_intersection(path_start, path_end, gate_p1, gate_p2)
    if point is None: return False
    eps = 1e-5
    if not (-eps <= s <= 1.0 + eps): return False
    if t < -eps or t > 1.0 + eps: return False  # Prevent the path from cutting behind the pocket

    margin = 0.1
    if dist(point, gate_p1) < (ball_radius - margin) or dist(point, gate_p2) < (ball_radius - margin):
        return False
    return True