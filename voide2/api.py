"""FastAPI surface for telemetry replay and twin snapshots."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .schema import default_chiller_asset
from .scenarios import MaintenanceScenario, rank_scenarios
from .service import run_replay
from .telemetry import read_csv_events, replay_events
from .twin import AssetRegistry, DigitalTwin

app = FastAPI(
    title="V.O.I.D.E. 2.0 API",
    version="2.0.0",
    description="Industrial telemetry replay and decision-support API. Not a safety controller.",
)
_twins: dict[str, DigitalTwin] = {}


class CsvRequest(BaseModel):
    csv_path: str


class ScenarioRequest(BaseModel):
    asset_id: str
    scenarios: list[dict[str, Any]] = Field(default_factory=list)


def _load(csv_path: str) -> DigitalTwin:
    path = Path(csv_path).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(status_code=400, detail="csv_path must reference an existing readable CSV")
    try:
        import pandas as pd
        frame = pd.read_csv(path, usecols=["asset_id"])
        registry = AssetRegistry()
        events = []
        for asset_id in sorted(frame["asset_id"].dropna().unique().tolist()):
            spec = default_chiller_asset(str(asset_id))
            registry.register(spec)
            events.extend(read_csv_events(path, spec))
        twin = DigitalTwin(registry)
        twin.replay(replay_events(events))
        _twins[path.as_posix()] = twin
        return twin
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "2.0.0"}


@app.post("/replay")
def replay(payload: CsvRequest) -> dict[str, Any]:
    path = Path(payload.csv_path).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(status_code=400, detail="csv_path must reference an existing readable CSV")
    try:
        return run_replay(path)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/fleet")
def fleet() -> dict[str, Any]:
    if not _twins:
        return {"asset_count": 0, "assets": []}
    return next(reversed(_twins.values())).fleet_snapshot()


@app.post("/load-twin")
def load_twin(payload: CsvRequest) -> dict[str, Any]:
    return _load(payload.csv_path).fleet_snapshot()


@app.post("/scenarios")
def scenarios(request: ScenarioRequest) -> list[dict[str, Any]]:
    twin = next(reversed(_twins.values()), None) if _twins else None
    if twin is None:
        raise HTTPException(status_code=409, detail="load a twin before evaluating scenarios")
    state = twin.states.get(request.asset_id)
    if state is None:
        raise HTTPException(status_code=404, detail="asset not found")
    try:
        parsed = [MaintenanceScenario(**item) for item in request.scenarios]
        if not parsed:
            raise ValueError("at least one scenario is required")
        return rank_scenarios(state, parsed)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
