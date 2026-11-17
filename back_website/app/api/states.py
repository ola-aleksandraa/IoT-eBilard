"""Table state database routes (ported from PoC/table-state-database) and watcher views."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..table_state import models, schemas
from ..table_state.database import get_db

router = APIRouter(prefix="/api/v1")


def _get_state_or_404(db: Session, state_id: uuid.UUID) -> models.TableState:
    state = db.get(models.TableState, state_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "table state not found")
    return state


def _to_ball_rows(balls: list[schemas.BallIn]) -> list[models.Ball]:
    return [models.Ball(**b.model_dump()) for b in balls]


@router.post("/states", response_model=schemas.TableStateOut, status_code=status.HTTP_201_CREATED, tags=["Table states"])
def create_state(payload: schemas.TableStateCreate, db: Session = Depends(get_db)):
    """Store a new table snapshot together with its balls."""
    data = payload.model_dump(exclude={"balls"}, exclude_none=True)
    state = models.TableState(**data)
    state.balls = _to_ball_rows(payload.balls)
    state.sync_ball_count()
    db.add(state)
    db.commit()
    return state


@router.get("/states", response_model=list[schemas.TableStateSummary], tags=["Table states"])
def list_states(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """List snapshots, newest first."""
    stmt = select(models.TableState).order_by(models.TableState.captured_at.desc()).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.get("/states/latest", response_model=schemas.TableStateOut, tags=["Table states"])
def get_latest_state(db: Session = Depends(get_db)):
    stmt = select(models.TableState).order_by(models.TableState.captured_at.desc()).limit(1)
    state = db.scalars(stmt).first()
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no table states stored yet")
    return state


@router.get("/states/watcher", response_model=schemas.WatcherStatus, tags=["Table states"])
def watcher_status(request: Request):
    """Camera watcher phase (initializing / stable / settling), window fill and last error."""
    watcher = request.app.state.watcher
    if watcher is None:
        return schemas.WatcherStatus(enabled=False, running=False, phase="disabled", window_size=0, window_filled=0,
                                     calibrated=False, frames_seen=0, states_stored=0, last_state_id=None, last_error=None)
    return watcher.status()


@router.get("/states/{state_id}", response_model=schemas.TableStateOut, tags=["Table states"])
def get_state(state_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_state_or_404(db, state_id)


@router.put("/states/{state_id}/balls", response_model=schemas.TableStateOut, tags=["Table states"])
def replace_balls(state_id: uuid.UUID, payload: schemas.BallsReplace, db: Session = Depends(get_db)):
    """Replace all balls of a snapshot (e.g. after a corrected detection)."""
    state = _get_state_or_404(db, state_id)
    try:
        schemas.validate_balls(payload.balls, state.table_width_cm, state.table_length_cm)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    state.balls = _to_ball_rows(payload.balls)  # orphans are deleted by the cascade
    state.sync_ball_count()
    db.commit()
    return state


@router.delete("/states/{state_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Table states"])
def delete_state(state_id: uuid.UUID, db: Session = Depends(get_db)):
    state = _get_state_or_404(db, state_id)
    db.delete(state)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/table/live", response_model=schemas.LiveTable, tags=["Table states"],
            responses={503: {"description": "Watcher disabled or no frame captured yet"}})
def live_table(request: Request):
    """Latest frame the watcher received from the Pi (normalized coordinates, frame-local ids)."""
    watcher = request.app.state.watcher
    if watcher is None:
        raise HTTPException(503, "table watcher is disabled (set TABLE_WATCH_ENABLED=1)")
    if watcher.live is None:
        raise HTTPException(503, "no camera frame received yet", headers={"Retry-After": "1"})
    return watcher.live
