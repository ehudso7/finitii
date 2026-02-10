"""Cheat Code service: full lifecycle management.

Lifecycle: Recommend → Start → Pause/Resume → Complete → Archive/Abandon
All state transitions audit-logged.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeRun,
    Recommendation,
    RunStatus,
    StepRun,
)
from app.services import audit_service


async def start_run(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    ip_address: str | None = None,
) -> CheatCodeRun:
    """Start a cheat code run from a recommendation.

    Creates a CheatCodeRun + StepRun records for each step.
    """
    # Get the recommendation
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == user_id,
        )
    )
    rec = result.scalar_one()

    # Get the cheat code definition
    result = await db.execute(
        select(CheatCodeDefinition).where(
            CheatCodeDefinition.id == rec.cheat_code_id
        )
    )
    definition = result.scalar_one()

    total_steps = len(definition.steps)

    # Create the run
    run = CheatCodeRun(
        user_id=user_id,
        cheat_code_id=definition.id,
        recommendation_id=recommendation_id,
        status=RunStatus.in_progress,
        started_at=datetime.now(timezone.utc),
        total_steps=total_steps,
        completed_steps=0,
    )
    db.add(run)
    await db.flush()

    # Create step runs
    for step_data in definition.steps:
        step = StepRun(
            run_id=run.id,
            step_number=step_data["step_number"],
            status=RunStatus.not_started,
        )
        db.add(step)

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="cheatcode.run_started",
        entity_type="CheatCodeRun",
        entity_id=run.id,
        action="start",
        detail={
            "cheat_code": definition.code,
            "total_steps": total_steps,
            "recommendation_id": str(recommendation_id),
        },
        ip_address=ip_address,
    )

    return run


async def complete_step(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    step_number: int,
    notes: str | None = None,
    ip_address: str | None = None,
) -> StepRun:
    """Complete a step in a cheat code run.

    Returns the updated StepRun.
    Also updates the parent run's completed_steps count.
    If all steps completed, marks the run as completed.
    """
    # Verify the run belongs to this user and is in progress
    run_result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
            CheatCodeRun.status == RunStatus.in_progress,
        )
    )
    run = run_result.scalar_one()

    # Get the step
    step_result = await db.execute(
        select(StepRun).where(
            StepRun.run_id == run_id,
            StepRun.step_number == step_number,
        )
    )
    step = step_result.scalar_one()

    # Mark step as completed
    now = datetime.now(timezone.utc)
    if step.started_at is None:
        step.started_at = now
    step.completed_at = now
    step.status = RunStatus.completed
    step.notes = notes
    await db.flush()

    # Update run's completed_steps count
    completed_result = await db.execute(
        select(StepRun).where(
            StepRun.run_id == run_id,
            StepRun.status == RunStatus.completed,
        )
    )
    completed_steps = len(completed_result.scalars().all())
    run.completed_steps = completed_steps

    # If all steps completed, mark run as completed
    if completed_steps >= run.total_steps:
        run.status = RunStatus.completed
        run.completed_at = now

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="cheatcode.step_completed",
        entity_type="StepRun",
        entity_id=step.id,
        action="complete_step",
        detail={
            "run_id": str(run_id),
            "step_number": step_number,
            "completed_steps": completed_steps,
            "total_steps": run.total_steps,
            "run_completed": run.status == RunStatus.completed,
        },
        ip_address=ip_address,
    )

    return step


async def get_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CheatCodeRun:
    """Get a specific run for a user."""
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
        )
    )
    return result.scalar_one()


async def get_run_steps(
    db: AsyncSession,
    run_id: uuid.UUID,
) -> list[StepRun]:
    """Get all steps for a run."""
    result = await db.execute(
        select(StepRun)
        .where(StepRun.run_id == run_id)
        .order_by(StepRun.step_number.asc())
    )
    return list(result.scalars().all())


async def get_user_runs(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: RunStatus | None = None,
) -> list[CheatCodeRun]:
    """Get all runs for a user, optionally filtered by status."""
    stmt = (
        select(CheatCodeRun)
        .where(CheatCodeRun.user_id == user_id)
        .order_by(CheatCodeRun.started_at.desc())
    )
    if status is not None:
        stmt = stmt.where(CheatCodeRun.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def pause_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> CheatCodeRun:
    """Pause an in-progress run."""
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
            CheatCodeRun.status == RunStatus.in_progress,
        )
    )
    run = result.scalar_one()
    run.status = RunStatus.paused
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="cheatcode.run_paused",
        entity_type="CheatCodeRun",
        entity_id=run.id,
        action="pause",
        detail={"completed_steps": run.completed_steps, "total_steps": run.total_steps},
        ip_address=ip_address,
    )

    return run


async def resume_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> CheatCodeRun:
    """Resume a paused run."""
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
            CheatCodeRun.status == RunStatus.paused,
        )
    )
    run = result.scalar_one()
    run.status = RunStatus.in_progress
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="cheatcode.run_resumed",
        entity_type="CheatCodeRun",
        entity_id=run.id,
        action="resume",
        ip_address=ip_address,
    )

    return run


async def abandon_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str | None = None,
    ip_address: str | None = None,
) -> CheatCodeRun:
    """Abandon a run (user gives up or decides not to complete)."""
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status in (RunStatus.completed, RunStatus.archived):
        raise ValueError(
            f"Cannot abandon run with status '{run.status.value}'"
        )

    run.status = RunStatus.abandoned
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="cheatcode.run_abandoned",
        entity_type="CheatCodeRun",
        entity_id=run.id,
        action="abandon",
        detail={
            "reason": reason,
            "completed_steps": run.completed_steps,
            "total_steps": run.total_steps,
        },
        ip_address=ip_address,
    )

    return run


async def archive_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> CheatCodeRun:
    """Archive a completed run."""
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status != RunStatus.completed:
        raise ValueError(
            f"Cannot archive run with status '{run.status.value}', must be 'completed'"
        )

    run.status = RunStatus.archived
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="cheatcode.run_archived",
        entity_type="CheatCodeRun",
        entity_id=run.id,
        action="archive",
        ip_address=ip_address,
    )

    return run
