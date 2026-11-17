"""Conversion between normalized detector layouts and stored table states (cm)."""

import uuid
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import BALL_TYPE_TO_KIND, KIND_TO_BALL_TYPE, Ball, TableState, utcnow
from .stability import SettledLayout, TrackedBall

# back_raspberry: x along the long side (cloth width in the image), y along the short side.
# Database:      length = along the table (long side), width = across it (short side).


def _clamp(value: float, upper: float) -> float:
    return min(max(value, 0.0), upper)


def store_layout(session_factory: sessionmaker[Session], layout: SettledLayout,
                 table_width_cm: float, table_length_cm: float) -> uuid.UUID:
    captured_at = layout.acquired_at
    if captured_at is not None and captured_at.tzinfo is not None:
        captured_at = captured_at.astimezone(timezone.utc).replace(tzinfo=None)  # stored as naive UTC
    state = TableState(
        captured_at=captured_at or utcnow(),
        table_width_cm=table_width_cm,
        table_length_cm=table_length_cm,
        image_ref=f"pi-frame:{layout.frame_id}" if layout.frame_id else None,
        balls=[Ball(ball_type=KIND_TO_BALL_TYPE[b.kind],
                    location_width_cm=round(_clamp(b.y * table_width_cm, table_width_cm), 2),
                    location_length_cm=round(_clamp(b.x * table_length_cm, table_length_cm), 2))
               for b in layout.balls],
    )
    state.sync_ball_count()
    with session_factory() as db:
        db.add(state)
        db.commit()
        return state.state_id


def load_baseline(session_factory: sessionmaker[Session], table_width_cm: float, table_length_cm: float,
                  radius: float) -> tuple[TrackedBall, ...] | None:
    """Latest stored layout as the watcher's starting point (only if stored for the same table size)."""
    with session_factory() as db:
        state = db.scalars(select(TableState).order_by(TableState.captured_at.desc()).limit(1)).first()
        if state is None or (state.table_width_cm, state.table_length_cm) != (table_width_cm, table_length_cm):
            return None
        return tuple(TrackedBall(kind=BALL_TYPE_TO_KIND[b.ball_type],
                                 x=b.location_length_cm / table_length_cm,
                                 y=b.location_width_cm / table_width_cm,
                                 radius=radius)
                     for b in state.balls)
