import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class BallType(str, enum.Enum):
    FULL = "FULL"
    HALF = "HALF"
    WHITE = "WHITE"  # the cue ball: neither full nor half


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TableState(Base):
    """One snapshot of the table; parent of all balls in that snapshot."""

    __tablename__ = "table_state"
    __table_args__ = (
        CheckConstraint("table_width_cm > 0", name="ck_table_width_positive"),
        CheckConstraint("table_length_cm > 0", name="ck_table_length_positive"),
        CheckConstraint("ball_count >= 0", name="ck_ball_count_nonneg"),
    )

    state_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    ball_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    table_width_cm: Mapped[float] = mapped_column(Float, nullable=False)
    table_length_cm: Mapped[float] = mapped_column(Float, nullable=False)
    image_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)

    balls: Mapped[list["Ball"]] = relationship(
        back_populates="state",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Ball.ball_id",
    )

    def sync_ball_count(self) -> None:
        """Keep ball_count equal to the number of related Ball rows."""
        self.ball_count = len(self.balls)


class Ball(Base):
    """A ball on the table at the moment of the snapshot (pocketed balls are absent)."""

    __tablename__ = "ball"
    __table_args__ = (
        CheckConstraint("location_width_cm >= 0", name="ck_ball_width_nonneg"),
        CheckConstraint("location_length_cm >= 0", name="ck_ball_length_nonneg"),
    )

    ball_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    state_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("table_state.state_id", ondelete="CASCADE"), index=True, nullable=False
    )
    ball_type: Mapped[BallType] = mapped_column(Enum(BallType), nullable=False)
    location_width_cm: Mapped[float] = mapped_column(Float, nullable=False)
    location_length_cm: Mapped[float] = mapped_column(Float, nullable=False)

    state: Mapped[TableState] = relationship(back_populates="balls")