"""Phase 3 model tests: CheatCodeOutcome, expanded RunStatus."""

import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeOutcome,
    CheatCodeRun,
    OutcomeType,
    RunStatus,
    VerificationStatus,
)
from app.models.user import User


async def _create_user(db: AsyncSession) -> User:
    user = User(email="p3model@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_definition(db: AsyncSession) -> CheatCodeDefinition:
    defn = CheatCodeDefinition(
        code="P3-TEST",
        title="Phase 3 Test Code",
        description="Test description",
        category="save_money",
        difficulty="quick_win",
        estimated_minutes=5,
        steps=[{"step_number": 1, "title": "Step 1", "description": "Do it"}],
        potential_savings_min=Decimal("10.00"),
        potential_savings_max=Decimal("50.00"),
    )
    db.add(defn)
    await db.flush()
    return defn


async def _create_completed_run(
    db: AsyncSession, user: User, defn: CheatCodeDefinition
) -> CheatCodeRun:
    from datetime import datetime, timezone

    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.completed,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_steps=1,
        completed_steps=1,
    )
    db.add(run)
    await db.flush()
    return run


@pytest.mark.asyncio
async def test_outcome_model_create(db_session: AsyncSession):
    """CheatCodeOutcome can be created with all fields."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session)
    run = await _create_completed_run(db_session, user, defn)

    outcome = CheatCodeOutcome(
        run_id=run.id,
        user_id=user.id,
        outcome_type=OutcomeType.user_reported,
        reported_savings=Decimal("25.00"),
        reported_savings_period="monthly",
        verification_status=VerificationStatus.unverified,
        notes="Cancelled my streaming sub",
        user_satisfaction=4,
    )
    db_session.add(outcome)
    await db_session.flush()

    result = await db_session.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.id == outcome.id)
    )
    fetched = result.scalar_one()
    assert fetched.outcome_type == OutcomeType.user_reported
    assert fetched.reported_savings == Decimal("25.00")
    assert fetched.reported_savings_period == "monthly"
    assert fetched.verification_status == VerificationStatus.unverified
    assert fetched.notes == "Cancelled my streaming sub"
    assert fetched.user_satisfaction == 4


@pytest.mark.asyncio
async def test_outcome_type_enum(db_session: AsyncSession):
    """OutcomeType enum has user_reported and inferred."""
    assert OutcomeType.user_reported.value == "user_reported"
    assert OutcomeType.inferred.value == "inferred"


@pytest.mark.asyncio
async def test_verification_status_enum(db_session: AsyncSession):
    """VerificationStatus enum has correct values."""
    assert VerificationStatus.unverified.value == "unverified"
    assert VerificationStatus.verified.value == "verified"
    assert VerificationStatus.disputed.value == "disputed"


@pytest.mark.asyncio
async def test_run_status_has_paused_and_abandoned(db_session: AsyncSession):
    """RunStatus enum includes paused and abandoned (Phase 3 additions)."""
    assert RunStatus.paused.value == "paused"
    assert RunStatus.abandoned.value == "abandoned"
    # All original values still present
    assert RunStatus.not_started.value == "not_started"
    assert RunStatus.in_progress.value == "in_progress"
    assert RunStatus.completed.value == "completed"
    assert RunStatus.archived.value == "archived"


@pytest.mark.asyncio
async def test_outcome_inferred_fields(db_session: AsyncSession):
    """CheatCodeOutcome supports inferred savings data."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session)
    run = await _create_completed_run(db_session, user, defn)

    outcome = CheatCodeOutcome(
        run_id=run.id,
        user_id=user.id,
        outcome_type=OutcomeType.inferred,
        inferred_savings=Decimal("15.99"),
        inferred_method="recurring_pattern_removed",
        verification_status=VerificationStatus.unverified,
    )
    db_session.add(outcome)
    await db_session.flush()

    result = await db_session.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.id == outcome.id)
    )
    fetched = result.scalar_one()
    assert fetched.outcome_type == OutcomeType.inferred
    assert fetched.inferred_savings == Decimal("15.99")
    assert fetched.inferred_method == "recurring_pattern_removed"


@pytest.mark.asyncio
async def test_outcome_one_per_run(db_session: AsyncSession):
    """Only one outcome per run (unique constraint on run_id)."""
    from sqlalchemy.exc import IntegrityError

    user = await _create_user(db_session)
    defn = await _create_definition(db_session)
    run = await _create_completed_run(db_session, user, defn)

    outcome1 = CheatCodeOutcome(
        run_id=run.id,
        user_id=user.id,
        outcome_type=OutcomeType.user_reported,
        verification_status=VerificationStatus.unverified,
    )
    db_session.add(outcome1)
    await db_session.flush()

    outcome2 = CheatCodeOutcome(
        run_id=run.id,
        user_id=user.id,
        outcome_type=OutcomeType.user_reported,
        verification_status=VerificationStatus.unverified,
    )
    db_session.add(outcome2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
