import logging
import time
from contextlib import contextmanager

from .trajectory import find_all_shots
from .shot_scoring import (
    score_all_shots,
    get_top_shots,
    get_best_shot_per_ball,
)

from .table_types import (
    BilliardSceneState,
    TableStaticGeometry,
    TrajectoryResult,
)

from .config import settings

logger = logging.getLogger(__name__)


@contextmanager
def timer(label: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        logger.debug("%s took %.1f ms", label, (time.perf_counter() - start) * 1000)


def compute_trajectories(
    scene_state: BilliardSceneState,
    static_geometry: TableStaticGeometry,
    top_n: int = settings.module3_physics.pipeline.default_top_n,
    enable_bank_shots: bool = settings.module3_physics.pipeline.enable_bank_shots,
    min_score: float = settings.module3_physics.pipeline.min_valid_score,
    draw_best_per_ball: bool = settings.module3_physics.pipeline.draw_best_per_ball,
) -> TrajectoryResult:
    """
    Main pipeline for Module 3.

    STEP 1
        Generate all candidate shots.

    STEP 2
        Score every shot.

    STEP 3
        Select top shots.

    STEP 4
        Pack TrajectoryResult.

    Returns
    -------
    TrajectoryResult
    """

    if static_geometry is None:
        logger.error("[Module3] static_geometry is missing")
        raise ValueError("[Module3] TableStaticGeometry is required.")

    balls = scene_state.balls

    if not balls:
        logger.warning("[Module3] No balls detected.")
        return _empty_result(scene_state.frame_id)

    logger.info(
        f"[Module3] Computing trajectories "
        f"for {len(balls)} balls "
        f"(Frame: {scene_state.frame_id})..."
    )

    # ==========================================
    # STEP 1: FIND ALL SHOTS
    # ==========================================
    try:
        with timer("Module3 - Find All Shots"):
            all_shots = find_all_shots(
                balls=balls,
                table_layout=static_geometry,
            )

    except Exception as e:
        logger.exception(
            f"[Module3] Shot generation failed: {e}"
        )
        raise

    # Optional
    if not enable_bank_shots:
        all_shots = [
            shot
            for shot in all_shots
            if shot.shot_type == "direct"
            or shot.is_blocked
        ]

    # ==========================================
    # STEP 2: SCORE SHOTS
    # ==========================================
    try:
        with timer("Module3 - Score Shots"):
            score_all_shots(
                all_shots,
                static_geometry,
                balls,
            )

    except Exception as e:
        logger.exception(
            f"[Module3] Shot scoring failed: {e}"
        )
        raise

    # ==========================================
    # STEP 3: SELECT TOP SHOTS
    # ==========================================
    try:
        with timer("Module3 - Rank Top Shots"):

            if draw_best_per_ball:

                best_per_ball = get_best_shot_per_ball(
                    all_shots,
                    static_geometry,
                    balls,
                )

                top_shots = sorted(
                    best_per_ball.values(),
                    key=lambda s: s.score,
                    reverse=True,
                )

            else:

                top_shots = get_top_shots(
                    shots=all_shots,
                    top_n=top_n,
                    table_layout=static_geometry,
                    balls=balls,
                    min_score=min_score,
                    deduplicate=True,
                )

    except Exception as e:
        logger.exception(
            f"[Module3] Shot ranking failed: {e}"
        )
        raise

    # ==========================================
    # STEP 4: FIND CUE BALL TRACK ID
    # ==========================================
    cue_ball_track_id = None

    for ball in balls:
        if ball.class_name == "cue_ball":
            cue_ball_track_id = ball.track_id
            break

    # ==========================================
    # STEP 5: COLLECT BLOCKED SHOTS
    # ==========================================
    blocked_shots = [
        shot
        for shot in all_shots
        if shot.is_blocked
    ]

    # ==========================================
    # STEP 6: PACK RESULT
    # ==========================================
    trajectory_state = TrajectoryResult(
        scene_frame_id=scene_state.frame_id,
        cue_ball_track_id=cue_ball_track_id,
        top_shots=top_shots,
        blocked_shots=blocked_shots,
        all_shots_count=len(all_shots),
    )

    return trajectory_state


def _empty_result(
    frame_id: int,
) -> TrajectoryResult:
    """
    Return empty trajectory result.
    """

    logger.warning(
        "[Module3] Returning empty trajectory result."
    )

    return TrajectoryResult(
        scene_frame_id=frame_id,
        cue_ball_track_id=None,
        top_shots=[],
        blocked_shots=[],
        all_shots_count=0,
    )