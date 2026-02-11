"""Outcome service tests: report, infer, retrieve, totals."""

import pytest
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import OutcomeType, VerificationStatus
from app.models.user import User
from app.services import cheat_code_service, outcome_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="outcome@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_completed_run(db: AsyncSession, user: User):
    """Seed codes, compute top 3, start a run, complete all steps."""
    await seed_cheat_codes(db)
    recs = await ranking_service.compute_top_3(db, user.id)
    run = await cheat_code_service.start_run(
        db, user_id=user.id, recommendation_id=recs[0].id
    )
    for i in range(1, run.total_steps + 1):
        await cheat_code_service.complete_step(
            db, run_id=run.id, user_id=user.id, step_number=i
        )
    # Refetch to get updated status
    run = await cheat_code_service.get_run(db, run_id=run.id, user_id=user.id)
    return run, recs


@pytest.mark.asyncio
async def test_report_outcome(db_session: AsyncSession):
    """User can report savings from a completed run."""
    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    outcome = await outcome_service.report_outcome(
        db_session,
        run_id=run.id,
        user_id=user.id,
        reported_savings=Decimal("29.99"),
        reported_savings_period="monthly",
        notes="Cancelled Netflix",
        user_satisfaction=5,
    )

    assert outcome.outcome_type == OutcomeType.user_reported
    assert outcome.reported_savings == Decimal("29.99")
    assert outcome.reported_savings_period == "monthly"
    assert outcome.notes == "Cancelled Netflix"
    assert outcome.user_satisfaction == 5
    assert outcome.verification_status == VerificationStatus.unverified


@pytest.mark.asyncio
async def test_report_outcome_rejects_in_progress_run(db_session: AsyncSession):
    """Cannot report outcome on an in-progress run."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)
    recs = await ranking_service.compute_top_3(db_session, user.id)
    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs[0].id
    )

    with pytest.raises(ValueError, match="run status is 'in_progress'"):
        await outcome_service.report_outcome(
            db_session, run_id=run.id, user_id=user.id,
            reported_savings=Decimal("10.00"),
        )


@pytest.mark.asyncio
async def test_report_outcome_satisfaction_validation(db_session: AsyncSession):
    """Satisfaction must be 1-5."""
    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    with pytest.raises(ValueError, match="user_satisfaction must be between 1 and 5"):
        await outcome_service.report_outcome(
            db_session, run_id=run.id, user_id=user.id,
            user_satisfaction=0,
        )

    with pytest.raises(ValueError, match="user_satisfaction must be between 1 and 5"):
        await outcome_service.report_outcome(
            db_session, run_id=run.id, user_id=user.id,
            user_satisfaction=6,
        )


@pytest.mark.asyncio
async def test_report_outcome_period_validation(db_session: AsyncSession):
    """Savings period must be a valid value."""
    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    with pytest.raises(ValueError, match="reported_savings_period must be one of"):
        await outcome_service.report_outcome(
            db_session, run_id=run.id, user_id=user.id,
            reported_savings=Decimal("10.00"),
            reported_savings_period="daily",
        )


@pytest.mark.asyncio
async def test_report_outcome_idempotent_update(db_session: AsyncSession):
    """Reporting on the same run updates the existing outcome."""
    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    outcome1 = await outcome_service.report_outcome(
        db_session, run_id=run.id, user_id=user.id,
        reported_savings=Decimal("10.00"),
        reported_savings_period="monthly",
    )

    outcome2 = await outcome_service.report_outcome(
        db_session, run_id=run.id, user_id=user.id,
        reported_savings=Decimal("20.00"),
        reported_savings_period="monthly",
        user_satisfaction=4,
    )

    # Same outcome record, updated
    assert outcome2.id == outcome1.id
    assert outcome2.reported_savings == Decimal("20.00")
    assert outcome2.user_satisfaction == 4


@pytest.mark.asyncio
async def test_infer_outcome(db_session: AsyncSession):
    """System can infer outcome from data."""
    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    outcome = await outcome_service.infer_outcome(
        db_session,
        run_id=run.id,
        user_id=user.id,
        inferred_savings=Decimal("15.99"),
        inferred_method="recurring_pattern_removed",
    )

    assert outcome.outcome_type == OutcomeType.inferred
    assert outcome.inferred_savings == Decimal("15.99")
    assert outcome.inferred_method == "recurring_pattern_removed"


@pytest.mark.asyncio
async def test_get_outcome_for_run(db_session: AsyncSession):
    """Can retrieve outcome by run ID."""
    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    await outcome_service.report_outcome(
        db_session, run_id=run.id, user_id=user.id,
        reported_savings=Decimal("50.00"),
    )

    fetched = await outcome_service.get_outcome_for_run(db_session, run.id)
    assert fetched is not None
    assert fetched.reported_savings == Decimal("50.00")


@pytest.mark.asyncio
async def test_get_outcome_for_run_none(db_session: AsyncSession):
    """Returns None if no outcome exists for run."""
    import uuid
    result = await outcome_service.get_outcome_for_run(db_session, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_outcomes_for_user(db_session: AsyncSession):
    """Can retrieve all outcomes for a user."""
    user = await _create_user(db_session)
    run, recs = await _create_completed_run(db_session, user)

    await outcome_service.report_outcome(
        db_session, run_id=run.id, user_id=user.id,
        reported_savings=Decimal("25.00"),
    )

    outcomes = await outcome_service.get_outcomes_for_user(db_session, user.id)
    assert len(outcomes) == 1
    assert outcomes[0].reported_savings == Decimal("25.00")


@pytest.mark.asyncio
async def test_total_reported_savings(db_session: AsyncSession):
    """Total reported savings sums across outcomes."""
    user = await _create_user(db_session)
    run, recs = await _create_completed_run(db_session, user)

    await outcome_service.report_outcome(
        db_session, run_id=run.id, user_id=user.id,
        reported_savings=Decimal("25.00"),
        reported_savings_period="monthly",
    )

    total = await outcome_service.get_total_reported_savings(db_session, user.id)
    assert total == Decimal("25.00")


@pytest.mark.asyncio
async def test_total_reported_savings_zero_when_none(db_session: AsyncSession):
    """Total is 0 when user has no outcomes."""
    user = await _create_user(db_session)
    total = await outcome_service.get_total_reported_savings(db_session, user.id)
    assert total == Decimal("0.00")


@pytest.mark.asyncio
async def test_report_outcome_audit_logged(db_session: AsyncSession):
    """Outcome reporting must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    run, _ = await _create_completed_run(db_session, user)

    await outcome_service.report_outcome(
        db_session, run_id=run.id, user_id=user.id,
        reported_savings=Decimal("15.00"),
        user_satisfaction=3,
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "outcome.reported",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].detail["reported_savings"] == "15.00"
