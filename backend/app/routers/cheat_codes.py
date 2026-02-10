"""Cheat code routes: Top 3, lifecycle (start/pause/resume/abandon/archive), outcomes."""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.cheat_code import CheatCodeDefinition, Recommendation
from app.models.user import User
from app.schemas.cheat_code import (
    AbandonRunRequest,
    CheatCodeRead,
    CompleteStepRequest,
    OutcomeRead,
    RecommendationRead,
    ReportOutcomeRequest,
    RunRead,
    StartRunRequest,
    StepRunRead,
)
from app.services import cheat_code_service, outcome_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes

router = APIRouter(prefix="/cheat-codes", tags=["cheat-codes"])


@router.post("/seed")
async def seed(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seed cheat code definitions (idempotent)."""
    definitions = await seed_cheat_codes(db)
    return {"seeded": len(definitions)}


@router.post("/top-3")
async def compute_top_3(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute and return the Top 3 Moves for the current user."""
    ip = request.client.host if request.client else None

    # Ensure cheat codes are seeded
    await seed_cheat_codes(db)

    recommendations = await ranking_service.compute_top_3(
        db, current_user.id, ip_address=ip
    )

    # Build response with cheat code details
    result = []
    for rec in recommendations:
        def_result = await db.execute(
            select(CheatCodeDefinition).where(
                CheatCodeDefinition.id == rec.cheat_code_id
            )
        )
        defn = def_result.scalar_one()

        result.append({
            "id": str(rec.id),
            "rank": rec.rank,
            "explanation": rec.explanation,
            "confidence": rec.confidence,
            "is_quick_win": rec.is_quick_win,
            "cheat_code": {
                "id": str(defn.id),
                "code": defn.code,
                "title": defn.title,
                "description": defn.description,
                "category": defn.category.value,
                "difficulty": defn.difficulty.value,
                "estimated_minutes": defn.estimated_minutes,
                "steps": defn.steps,
                "potential_savings_min": str(defn.potential_savings_min)
                if defn.potential_savings_min else None,
                "potential_savings_max": str(defn.potential_savings_max)
                if defn.potential_savings_max else None,
            },
        })

    return result


@router.get("/recommendations")
async def get_recommendations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get existing Top 3 recommendations (without recomputing)."""
    recommendations = await ranking_service.get_recommendations(db, current_user.id)

    result = []
    for rec in recommendations:
        def_result = await db.execute(
            select(CheatCodeDefinition).where(
                CheatCodeDefinition.id == rec.cheat_code_id
            )
        )
        defn = def_result.scalar_one()

        result.append({
            "id": str(rec.id),
            "rank": rec.rank,
            "explanation": rec.explanation,
            "confidence": rec.confidence,
            "is_quick_win": rec.is_quick_win,
            "cheat_code": {
                "id": str(defn.id),
                "code": defn.code,
                "title": defn.title,
                "description": defn.description,
                "category": defn.category.value,
                "difficulty": defn.difficulty.value,
                "estimated_minutes": defn.estimated_minutes,
                "steps": defn.steps,
                "potential_savings_min": str(defn.potential_savings_min)
                if defn.potential_savings_min else None,
                "potential_savings_max": str(defn.potential_savings_max)
                if defn.potential_savings_max else None,
            },
        })

    return result


@router.post("/runs", status_code=201)
async def start_run(
    body: StartRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a cheat code run from a recommendation."""
    ip = request.client.host if request.client else None

    run = await cheat_code_service.start_run(
        db,
        user_id=current_user.id,
        recommendation_id=body.recommendation_id,
        ip_address=ip,
    )

    steps = await cheat_code_service.get_run_steps(db, run.id)

    # Get cheat code definition
    def_result = await db.execute(
        select(CheatCodeDefinition).where(
            CheatCodeDefinition.id == run.cheat_code_id
        )
    )
    defn = def_result.scalar_one()

    return {
        "id": str(run.id),
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "total_steps": run.total_steps,
        "completed_steps": run.completed_steps,
        "cheat_code": {
            "id": str(defn.id),
            "code": defn.code,
            "title": defn.title,
        },
        "steps": [
            {
                "step_number": s.step_number,
                "status": s.status.value,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "notes": s.notes,
            }
            for s in steps
        ],
    }


@router.post("/runs/{run_id}/steps/complete")
async def complete_step(
    run_id: str,
    body: CompleteStepRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete a step in a cheat code run."""
    ip = request.client.host if request.client else None

    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    step = await cheat_code_service.complete_step(
        db,
        run_id=rid,
        user_id=current_user.id,
        step_number=body.step_number,
        notes=body.notes,
        ip_address=ip,
    )

    # Get updated run state
    run = await cheat_code_service.get_run(db, run_id=rid, user_id=current_user.id)

    return {
        "step": {
            "step_number": step.step_number,
            "status": step.status.value,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            "notes": step.notes,
        },
        "run": {
            "id": str(run.id),
            "status": run.status.value,
            "completed_steps": run.completed_steps,
            "total_steps": run.total_steps,
        },
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get run status with step details."""
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    run = await cheat_code_service.get_run(db, run_id=rid, user_id=current_user.id)
    steps = await cheat_code_service.get_run_steps(db, run.id)

    def_result = await db.execute(
        select(CheatCodeDefinition).where(
            CheatCodeDefinition.id == run.cheat_code_id
        )
    )
    defn = def_result.scalar_one()

    return {
        "id": str(run.id),
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "total_steps": run.total_steps,
        "completed_steps": run.completed_steps,
        "cheat_code": {
            "id": str(defn.id),
            "code": defn.code,
            "title": defn.title,
        },
        "steps": [
            {
                "step_number": s.step_number,
                "status": s.status.value,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "notes": s.notes,
            }
            for s in steps
        ],
    }


@router.get("/runs")
async def list_runs(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all runs for the current user, optionally filtered by status."""
    from app.models.cheat_code import RunStatus

    run_status = None
    if status:
        try:
            run_status = RunStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    runs = await cheat_code_service.get_user_runs(
        db, current_user.id, status=run_status
    )

    result = []
    for run in runs:
        def_result = await db.execute(
            select(CheatCodeDefinition).where(
                CheatCodeDefinition.id == run.cheat_code_id
            )
        )
        defn = def_result.scalar_one()
        result.append({
            "id": str(run.id),
            "status": run.status.value,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "total_steps": run.total_steps,
            "completed_steps": run.completed_steps,
            "cheat_code": {
                "id": str(defn.id),
                "code": defn.code,
                "title": defn.title,
            },
        })
    return result


@router.post("/runs/{run_id}/pause")
async def pause_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause an in-progress run."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    run = await cheat_code_service.pause_run(
        db, run_id=rid, user_id=current_user.id, ip_address=ip
    )
    return {"id": str(run.id), "status": run.status.value}


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume a paused run."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    run = await cheat_code_service.resume_run(
        db, run_id=rid, user_id=current_user.id, ip_address=ip
    )
    return {"id": str(run.id), "status": run.status.value}


@router.post("/runs/{run_id}/abandon")
async def abandon_run(
    run_id: str,
    request: Request,
    body: AbandonRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Abandon a run."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    reason = body.reason if body else None
    try:
        run = await cheat_code_service.abandon_run(
            db, run_id=rid, user_id=current_user.id, reason=reason, ip_address=ip
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"id": str(run.id), "status": run.status.value}


@router.post("/runs/{run_id}/archive")
async def archive_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive a completed run."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    try:
        run = await cheat_code_service.archive_run(
            db, run_id=rid, user_id=current_user.id, ip_address=ip
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"id": str(run.id), "status": run.status.value}


@router.post("/runs/{run_id}/outcome", status_code=201)
async def report_outcome(
    run_id: str,
    body: ReportOutcomeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Report the outcome of a completed cheat code run."""
    ip = request.client.host if request.client else None
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    try:
        outcome = await outcome_service.report_outcome(
            db,
            run_id=rid,
            user_id=current_user.id,
            reported_savings=body.reported_savings,
            reported_savings_period=body.reported_savings_period,
            notes=body.notes,
            user_satisfaction=body.user_satisfaction,
            ip_address=ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": str(outcome.id),
        "outcome_type": outcome.outcome_type.value,
        "reported_savings": str(outcome.reported_savings) if outcome.reported_savings else None,
        "reported_savings_period": outcome.reported_savings_period,
        "verification_status": outcome.verification_status.value,
        "user_satisfaction": outcome.user_satisfaction,
    }


@router.get("/runs/{run_id}/outcome")
async def get_outcome(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get outcome for a specific run."""
    try:
        rid = uuid_mod.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    outcome = await outcome_service.get_outcome_for_run(db, rid)
    if not outcome:
        raise HTTPException(status_code=404, detail="No outcome found for this run")

    return {
        "id": str(outcome.id),
        "run_id": str(outcome.run_id),
        "outcome_type": outcome.outcome_type.value,
        "reported_savings": str(outcome.reported_savings) if outcome.reported_savings else None,
        "reported_savings_period": outcome.reported_savings_period,
        "inferred_savings": str(outcome.inferred_savings) if outcome.inferred_savings else None,
        "inferred_method": outcome.inferred_method,
        "verification_status": outcome.verification_status.value,
        "notes": outcome.notes,
        "user_satisfaction": outcome.user_satisfaction,
    }


@router.get("/outcomes/summary")
async def outcomes_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a summary of all outcomes for the current user."""
    outcomes = await outcome_service.get_outcomes_for_user(db, current_user.id)
    total_savings = await outcome_service.get_total_reported_savings(
        db, current_user.id
    )

    return {
        "total_outcomes": len(outcomes),
        "total_reported_savings": str(total_savings),
        "outcomes": [
            {
                "id": str(o.id),
                "run_id": str(o.run_id),
                "outcome_type": o.outcome_type.value,
                "reported_savings": str(o.reported_savings) if o.reported_savings else None,
                "user_satisfaction": o.user_satisfaction,
            }
            for o in outcomes
        ],
    }
