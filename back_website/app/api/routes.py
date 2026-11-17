"""Numerical HTTP interface of the website backend. All application responses are JSON."""

from fastapi import APIRouter, Depends

from ..schemas import Category, PredictRequest, PredictionResult, Settings, ShotsRequest, ShotsResult, SimulateRequest, SimulationResult
from ..trajectory import plan_shots, predict_shot, simulate_motion
from .dependencies import processing_slot

router = APIRouter(prefix="/api/v1")
guarded = [Depends(processing_slot)]


@router.get("/settings", response_model=Settings, tags=["Configuration"])
def settings():
    """Default per-request detector settings."""
    return Settings()


@router.get("/categories", response_model=list[Category], tags=["Configuration"])
def categories():
    """Recognition vocabulary. The client selects colors, patterns and rendering."""
    return [Category(kind=kind, description=description) for kind, description in [
        ("cue", "Cue ball; at most one per frame."), ("eight", "Eight ball; at most one per frame."),
        ("solid", "Solid/full pattern."), ("striped", "Striped/half pattern."),
        ("unknown", "Located candidate with insufficient category evidence."),
    ]]


@router.post("/shots", response_model=ShotsResult, tags=["Shots"], dependencies=guarded)
def shots(options: ShotsRequest):
    """Rank direct and bank shots using normalized ball positions; return numerical paths."""
    return plan_shots(options.balls, options.table_ratio, options.top_n,
                      options.include_bank, options.include_blocked)


@router.post("/shots/predict", response_model=PredictionResult, response_model_exclude_unset=True, tags=["Shots"], dependencies=guarded)
def predict(options: PredictRequest):
    """Predict the first contact and pocket paths for a cue aim."""
    return predict_shot(options.balls, options.table_ratio, (options.aim_x, options.aim_y))


@router.post("/shots/simulate", response_model=SimulationResult, response_model_exclude_unset=True, tags=["Shots"], dependencies=guarded)
def simulate(options: SimulateRequest):
    """Roll out a cue aim with collisions, cushions and pots as time-sampled coordinates."""
    return simulate_motion(options.balls, options.table_ratio,
                           (options.aim_x, options.aim_y), options.power)
