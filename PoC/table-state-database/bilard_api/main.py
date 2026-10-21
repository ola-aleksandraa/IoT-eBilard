import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # use Alembic migrations in production
    yield


app = FastAPI(
    title="Bilard Table State API",
    lifespan=lifespan,
    docs_url=None,   # no interactive Swagger UI
    redoc_url=None,  # no ReDoc
)


def _get_state_or_404(db: Session, state_id: uuid.UUID) -> models.TableState:
    state = db.get(models.TableState, state_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "table state not found")
    return state


def _to_ball_rows(balls: list[schemas.BallIn]) -> list[models.Ball]:
    return [models.Ball(**b.model_dump()) for b in balls]


@app.post("/states", response_model=schemas.TableStateOut, status_code=status.HTTP_201_CREATED)
def create_state(payload: schemas.TableStateCreate, db: Session = Depends(get_db)):
    """Store a new table snapshot together with its balls."""
    data = payload.model_dump(exclude={"balls"}, exclude_none=True)
    state = models.TableState(**data)
    state.balls = _to_ball_rows(payload.balls)
    state.sync_ball_count()
    db.add(state)
    db.commit()
    return state


@app.get("/states", response_model=list[schemas.TableStateSummary])
def list_states(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List snapshots, newest first."""
    stmt = (
        select(models.TableState)
        .order_by(models.TableState.captured_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()


@app.get("/states/latest", response_model=schemas.TableStateOut)
def get_latest_state(db: Session = Depends(get_db)):
    stmt = select(models.TableState).order_by(models.TableState.captured_at.desc()).limit(1)
    state = db.scalars(stmt).first()
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no table states stored yet")
    return state


@app.get("/states/{state_id}", response_model=schemas.TableStateOut)
def get_state(state_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_state_or_404(db, state_id)


@app.put("/states/{state_id}/balls", response_model=schemas.TableStateOut)
def replace_balls(state_id: uuid.UUID, payload: schemas.BallsReplace, db: Session = Depends(get_db)):
    """Replace all balls of a snapshot (e.g. after a corrected detection)."""
    state = _get_state_or_404(db, state_id)
    try:
        schemas._validate_balls(payload.balls, state.table_width_cm, state.table_length_cm)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    state.balls = _to_ball_rows(payload.balls)  # orphans are deleted by the cascade
    state.sync_ball_count()
    db.commit()
    return state


@app.delete("/states/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_state(state_id: uuid.UUID, db: Session = Depends(get_db)):
    state = _get_state_or_404(db, state_id)
    db.delete(state)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)