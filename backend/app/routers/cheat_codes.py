"""Cheat code routes: Top 3, start run, complete step, get run status."""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.cheat_code import CheatCodeDefinition, Recommendation
from app.models.user import User
from app.schemas.cheat_code import (
    CheatCodeRead,
    CompleteStepRequest,
    RecommendationRead,
    RunRead,
    StartRunRequest,
    StepRunRead,
)
from app.services import cheat_code_service, ranking_service
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
