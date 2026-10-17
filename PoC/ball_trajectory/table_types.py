from dataclasses import dataclass
from typing import List, Tuple, Any

@dataclass
class TrackedBall:
    track_id: int
    class_name: str  # np. 'cue_ball', 'solid', 'striped'
    center_x: float
    center_y: float
    radius: float

@dataclass
class TableStaticGeometry:
    width: float
    height: float
    corners: List[Tuple[float, float]]
    pockets: List[Tuple[float, float]]
    pocket_gates: List[Tuple[Tuple[float, float], Tuple[float, float]]]
    cushions: List[Tuple[str, Tuple[float, float], Tuple[float, float]]]
    cushion_normals: List[Tuple[str, Tuple[float, float]]]
    solid_cushions: List[Tuple[str, Tuple[float, float], Tuple[float, float]]]

@dataclass
class BilliardSceneState:
    frame_id: int
    balls: List[TrackedBall]

@dataclass
class TrajectoryResult:
    scene_frame_id: int
    cue_ball_track_id: int
    top_shots: list
    blocked_shots: list
    all_shots_count: int