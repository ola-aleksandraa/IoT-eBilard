import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import BallType


class BallIn(BaseModel):
    ball_type: BallType
    location_width_cm: float = Field(ge=0)
    location_length_cm: float = Field(ge=0)


class BallOut(BallIn):
    model_config = ConfigDict(from_attributes=True)
    ball_id: uuid.UUID


def validate_balls(balls: list[BallIn], width: float | None, length: float | None) -> None:
    for unique in (BallType.WHITE, BallType.EIGHT):
        if sum(b.ball_type == unique for b in balls) > 1:
            raise ValueError(f"at most one {unique.value} ball is allowed")
    if width is None or length is None:
        return
    for b in balls:
        if b.location_width_cm > width or b.location_length_cm > length:
            raise ValueError("ball location lies outside the table")


class TableStateCreate(BaseModel):
    table_width_cm: float = Field(gt=0)
    table_length_cm: float = Field(gt=0)
    image_ref: str | None = Field(default=None, max_length=512)
    captured_at: datetime | None = None  # defaults to server time (UTC)
    balls: list[BallIn] = []

    @model_validator(mode="after")
    def check_balls(self):
        validate_balls(self.balls, self.table_width_cm, self.table_length_cm)
        return self


class BallsReplace(BaseModel):
    balls: list[BallIn]


class TableStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    state_id: uuid.UUID
    captured_at: datetime
    ball_count: int
    table_width_cm: float
    table_length_cm: float
    image_ref: str | None
    balls: list[BallOut]


class TableStateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    state_id: uuid.UUID
    captured_at: datetime
    ball_count: int
    image_ref: str | None


class LiveBall(BaseModel):
    """Same normalized coordinates as back_raspberry Ball and back_website ShotBall."""
    id: int
    kind: Literal["cue", "eight", "solid", "striped", "unknown"]
    x: float
    y: float
    radius: float


class LiveTable(BaseModel):
    """Latest camera frame seen by the watcher (not yet necessarily stored)."""
    table_status: Literal["detected", "searching"]
    frame_id: str | None
    acquired_at: datetime | None
    table_ratio: float
    balls: list[LiveBall]


class WatcherStatus(BaseModel):
    enabled: bool
    running: bool
    phase: Literal["disabled", "initializing", "stable", "settling"]
    window_size: int
    window_filled: int
    calibrated: bool
    frames_seen: int
    states_stored: int
    last_state_id: uuid.UUID | None
    last_error: str | None
