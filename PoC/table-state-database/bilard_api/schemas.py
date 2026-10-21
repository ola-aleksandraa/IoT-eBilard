import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import BallType


class BallIn(BaseModel):
    ball_type: BallType
    location_width_cm: float = Field(ge=0)
    location_length_cm: float = Field(ge=0)


class BallOut(BallIn):
    model_config = ConfigDict(from_attributes=True)
    ball_id: uuid.UUID


def _validate_balls(balls: list[BallIn], width: float | None, length: float | None) -> None:
    if sum(b.ball_type == BallType.WHITE for b in balls) > 1:
        raise ValueError("at most one WHITE (cue) ball is allowed")
    if width is None or length is None:
        return
    for b in balls:
        if b.location_width_cm > width or b.location_length_cm > length:
            raise ValueError("ball location lies outside the table")


class TableStateCreate(BaseModel):
    table_width_cm: float = Field(gt=0)
    table_length_cm: float = Field(gt=0)
    image_ref: str | None = Field(default=None, max_length=512)
    captured_at: datetime | None = None  # defaults to server time
    balls: list[BallIn] = []

    @model_validator(mode="after")
    def check_balls(self):
        _validate_balls(self.balls, self.table_width_cm, self.table_length_cm)
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