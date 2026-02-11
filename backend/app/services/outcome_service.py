"""Outcome service: report, infer, and retrieve cheat code outcomes.

Outcome types:
- user_reported: user manually reports savings/result after completing a cheat code
- inferred: system infers outcome from data (e.g. recurring charge disappeared)

No automation of money movement — outcomes are informational only.
All actions audit-logged.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeOutcome,
    CheatCodeRun,
    OutcomeType,
    RunStatus,
    VerificationStatus,
)
from app.services import audit_service


async def report_outcome(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    reported_savings: Decimal | None = None,
    reported_savings_period: str | None = None,
    notes: str | None = None,
    user_satisfaction: int | None = None,
    ip_address: str | None = None,
) -> CheatCodeOutcome:
    """User reports the outcome of a completed cheat code run.

    Validates: run must belong to user and be completed or archived.
    Satisfaction must be 1-5 if provided.
    """
    # Validate the run
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status not in (RunStatus.completed, RunStatus.archived):
        raise ValueError(
            f"Cannot report outcome: run status is '{run.status.value}', "
            "must be 'completed' or 'archived'"
        )

    if user_satisfaction is not None and not (1 <= user_satisfaction <= 5):
        raise ValueError("user_satisfaction must be between 1 and 5")

    if reported_savings_period is not None:
        valid_periods = ("monthly", "one_time", "annual", "weekly")
        if reported_savings_period not in valid_periods:
            raise ValueError(
                f"reported_savings_period must be one of: {valid_periods}"
            )

    # Check for existing outcome
    existing = await db.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.run_id == run_id)
    )
    existing_outcome = existing.scalar_one_or_none()

    if existing_outcome:
        # Update existing outcome with user-reported data
        existing_outcome.reported_savings = reported_savings
        existing_outcome.reported_savings_period = reported_savings_period
        existing_outcome.notes = notes
        existing_outcome.user_satisfaction = user_satisfaction
        if existing_outcome.outcome_type == OutcomeType.inferred:
            # Keep inferred data, add user-reported on top
            pass
        else:
            existing_outcome.outcome_type = OutcomeType.user_reported
        await db.flush()

        await audit_service.log_event(
            db,
            user_id=user_id,
            event_type="outcome.updated",
            entity_type="CheatCodeOutcome",
            entity_id=existing_outcome.id,
            action="update",
            detail={
                "run_id": str(run_id),
                "reported_savings": str(reported_savings) if reported_savings else None,
                "period": reported_savings_period,
                "satisfaction": user_satisfaction,
            },
            ip_address=ip_address,
        )

        return existing_outcome

    outcome = CheatCodeOutcome(
        run_id=run_id,
        user_id=user_id,
        outcome_type=OutcomeType.user_reported,
        reported_savings=reported_savings,
        reported_savings_period=reported_savings_period,
        notes=notes,
        user_satisfaction=user_satisfaction,
        verification_status=VerificationStatus.unverified,
    )
    db.add(outcome)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="outcome.reported",
        entity_type="CheatCodeOutcome",
        entity_id=outcome.id,
        action="report",
        detail={
            "run_id": str(run_id),
            "reported_savings": str(reported_savings) if reported_savings else None,
            "period": reported_savings_period,
            "satisfaction": user_satisfaction,
        },
        ip_address=ip_address,
    )

    return outcome


async def infer_outcome(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    inferred_savings: Decimal,
    inferred_method: str,
    ip_address: str | None = None,
) -> CheatCodeOutcome:
    """System infers outcome from data (e.g. recurring charge stopped).

    Validates: run must belong to user and be completed or archived.
    """
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.id == run_id,
            CheatCodeRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status not in (RunStatus.completed, RunStatus.archived):
        raise ValueError(
            f"Cannot infer outcome: run status is '{run.status.value}', "
            "must be 'completed' or 'archived'"
        )

    # Check for existing outcome
    existing = await db.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.run_id == run_id)
    )
    existing_outcome = existing.scalar_one_or_none()

    if existing_outcome:
        existing_outcome.inferred_savings = inferred_savings
        existing_outcome.inferred_method = inferred_method
        await db.flush()

        await audit_service.log_event(
            db,
            user_id=user_id,
            event_type="outcome.inferred_updated",
            entity_type="CheatCodeOutcome",
            entity_id=existing_outcome.id,
            action="infer_update",
            detail={
                "run_id": str(run_id),
                "inferred_savings": str(inferred_savings),
                "method": inferred_method,
            },
            ip_address=ip_address,
        )

        return existing_outcome

    outcome = CheatCodeOutcome(
        run_id=run_id,
        user_id=user_id,
        outcome_type=OutcomeType.inferred,
        inferred_savings=inferred_savings,
        inferred_method=inferred_method,
        verification_status=VerificationStatus.unverified,
    )
    db.add(outcome)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="outcome.inferred",
        entity_type="CheatCodeOutcome",
        entity_id=outcome.id,
        action="infer",
        detail={
            "run_id": str(run_id),
            "inferred_savings": str(inferred_savings),
            "method": inferred_method,
        },
        ip_address=ip_address,
    )

    return outcome


async def get_outcome_for_run(
    db: AsyncSession,
    run_id: uuid.UUID,
) -> CheatCodeOutcome | None:
    """Get the outcome for a specific run."""
    result = await db.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.run_id == run_id)
    )
    return result.scalar_one_or_none()


async def get_outcomes_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[CheatCodeOutcome]:
    """Get all outcomes for a user."""
    result = await db.execute(
        select(CheatCodeOutcome)
        .where(CheatCodeOutcome.user_id == user_id)
        .order_by(CheatCodeOutcome.created_at.desc())
    )
    return list(result.scalars().all())


async def get_total_reported_savings(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Decimal:
    """Calculate total user-reported savings across all outcomes."""
    outcomes = await get_outcomes_for_user(db, user_id)
    total = Decimal("0.00")
    for o in outcomes:
        if o.reported_savings:
            total += o.reported_savings
    return total
