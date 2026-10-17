from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class TrackedBall:
    track_id: int
    class_name: str  # 'cue_ball', 'eight', 'solid', 'striped', 'unknown'
    center_x: float
    center_y: float
    radius: float


@dataclass
class TableStaticGeometry:
    """All coordinates are in engine pixels (see service.ENGINE_WIDTH)."""
    width: float
    height: float
    ball_radius: float
    corners: np.ndarray  # (4, 2): TL, TR, BR, BL
    pockets: List[np.ndarray]
    pocket_gates: List[Tuple[np.ndarray, np.ndarray]]
    cushions: List[Tuple[str, np.ndarray, np.ndarray]]
    cushion_normals: List[Tuple[str, np.ndarray]]
    solid_cushions: List[Tuple[str, np.ndarray, np.ndarray]]


@dataclass
class BilliardSceneState:
    frame_id: int
    balls: List[TrackedBall]


@dataclass
class TrajectoryResult:
    scene_frame_id: int
    cue_ball_track_id: Optional[int]
    top_shots: list
    blocked_shots: list
    all_shots_count: int
