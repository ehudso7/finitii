"""Practice routes: scenarios, simulation, AAR, turn-into-plan.

Phase 7: Learn + Practice

Key PRD rules enforced:
- Practice confidence always capped at medium
- Practice-derived plans do NOT feed Top 3 ranking
- All interactions audit-logged
"""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.practice import (
    CompleteScenarioRequest,
    PracticePlanRead,
    ScenarioRead,
    ScenarioRunRead,
    SimulateRequest,
    StartScenarioRequest,
    TurnIntoPlanRequest,
)
from app.services import practice_service

router = APIRouter(prefix="/practice", tags=["practice"])


@router.get("/scenarios", response_model=list[ScenarioRead])
async def list_scenarios(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all active scenarios, optionally filtered by category."""
    scenarios = await practice_service.get_scenarios(db, category=category)
    return [ScenarioRead.model_validate(s) for s in scenarios]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific scenario by ID."""
    try:
        sid = uuid_mod.UUID(scenario_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario_id")
    try:
        scenario = await practice_service.get_scenario(db, scenario_id=sid)
    except Exception:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return ScenarioRead.model_validate(scenario)


@router.get("/runs", response_model=list[ScenarioRunRead])
async def list_runs(
    scenario_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all scenario runs for the current user."""
    sid = None
    if scenario_id:
        try:
            sid = uuid_mod.UUID(scenario_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scenario_id")
    runs = await practice_service.get_user_runs(
        db, user_id=current_user.id, scenario_id=sid
    )
    return [ScenarioRunRead.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=ScenarioRunRead)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific scenario run."""
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    try:
        run = await practice_service.get_run(
            db, run_id=rid, user_id=current_user.id
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Run not found")
    return ScenarioRunRead.model_validate(run)


@router.post("/start", response_model=ScenarioRunRead)
async def start_scenario(
    body: StartScenarioRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new scenario run."""
    ip = request.client.host if request.client else None
    try:
        sid = uuid_mod.UUID(body.scenario_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario_id")
    try:
        run = await practice_service.start_scenario(
            db, user_id=current_user.id, scenario_id=sid, ip_address=ip
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return ScenarioRunRead.model_validate(run)


@router.post("/simulate", response_model=ScenarioRunRead)
async def simulate(
    body: SimulateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run simulation with slider values. Confidence capped at medium."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(body.run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    try:
        run = await practice_service.simulate(
            db,
            user_id=current_user.id,
            run_id=rid,
            slider_values=body.slider_values,
            ip_address=ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ScenarioRunRead.model_validate(run)


@router.post("/complete", response_model=ScenarioRunRead)
async def complete_scenario(
    body: CompleteScenarioRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete a scenario run and generate After-Action Review."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(body.run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    try:
        run = await practice_service.complete_scenario(
            db, user_id=current_user.id, run_id=rid, ip_address=ip
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ScenarioRunRead.model_validate(run)


@router.post("/turn-into-plan", response_model=PracticePlanRead)
async def turn_into_plan(
    body: TurnIntoPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bridge practice output to coach plan. Does NOT feed Top 3 ranking."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(body.run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    try:
        plan = await practice_service.turn_into_plan(
            db, user_id=current_user.id, run_id=rid, ip_address=ip
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PracticePlanRead(**plan)
