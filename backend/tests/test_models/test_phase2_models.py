"""Phase 2 model tests: OnboardingState, Goal, UserConstraint, CheatCode models."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeCategory,
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeRun,
    Recommendation,
    RunStatus,
    StepRun,
)
from app.models.goal import Goal, GoalPriority, GoalType, UserConstraint
from app.models.onboarding import OnboardingState, OnboardingStep
from app.models.user import User


async def _create_user(db: AsyncSession, email: str = "model@test.com") -> User:
    user = User(email=email, password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_onboarding_state_creation(db_session: AsyncSession):
    user = await _create_user(db_session)
    state = OnboardingState(
        user_id=user.id,
        current_step=OnboardingStep.consent,
    )
    db_session.add(state)
    await db_session.flush()

    result = await db_session.execute(
        select(OnboardingState).where(OnboardingState.user_id == user.id)
    )
    loaded = result.scalar_one()
    assert loaded.current_step == OnboardingStep.consent
    assert loaded.consent_completed_at is None
    assert loaded.first_win_completed_at is None


@pytest.mark.asyncio
async def test_onboarding_state_unique_per_user(db_session: AsyncSession):
    user = await _create_user(db_session)
    state1 = OnboardingState(user_id=user.id, current_step=OnboardingStep.consent)
    db_session.add(state1)
    await db_session.flush()

    state2 = OnboardingState(user_id=user.id, current_step=OnboardingStep.goals)
    db_session.add(state2)
    with pytest.raises(Exception):  # unique constraint violation
        await db_session.flush()


@pytest.mark.asyncio
async def test_goal_creation(db_session: AsyncSession):
    user = await _create_user(db_session)
    goal = Goal(
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Save $1000",
        target_amount=Decimal("1000.00"),
        priority=GoalPriority.high,
    )
    db_session.add(goal)
    await db_session.flush()

    result = await db_session.execute(
        select(Goal).where(Goal.user_id == user.id)
    )
    loaded = result.scalar_one()
    assert loaded.title == "Save $1000"
    assert loaded.goal_type == GoalType.save_money
    assert loaded.current_amount == Decimal("0.00")
    assert loaded.is_active is True


@pytest.mark.asyncio
async def test_user_constraint_creation(db_session: AsyncSession):
    user = await _create_user(db_session)
    constraint = UserConstraint(
        user_id=user.id,
        constraint_type="monthly_income",
        label="Salary",
        amount=Decimal("5000.00"),
    )
    db_session.add(constraint)
    await db_session.flush()

    result = await db_session.execute(
        select(UserConstraint).where(UserConstraint.user_id == user.id)
    )
    loaded = result.scalar_one()
    assert loaded.constraint_type == "monthly_income"
    assert loaded.amount == Decimal("5000.00")


@pytest.mark.asyncio
async def test_cheat_code_definition_creation(db_session: AsyncSession):
    defn = CheatCodeDefinition(
        code="TEST-001",
        title="Test Cheat Code",
        description="A test cheat code",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=10,
        steps=[
            {"step_number": 1, "title": "Step 1", "description": "Do step 1", "estimated_minutes": 5},
            {"step_number": 2, "title": "Step 2", "description": "Do step 2", "estimated_minutes": 5},
        ],
        potential_savings_min=Decimal("5.00"),
        potential_savings_max=Decimal("50.00"),
    )
    db_session.add(defn)
    await db_session.flush()

    result = await db_session.execute(
        select(CheatCodeDefinition).where(CheatCodeDefinition.code == "TEST-001")
    )
    loaded = result.scalar_one()
    assert loaded.difficulty == CheatCodeDifficulty.quick_win
    assert loaded.estimated_minutes == 10
    assert len(loaded.steps) == 2
    assert loaded.is_active is True


@pytest.mark.asyncio
async def test_cheat_code_unique_code(db_session: AsyncSession):
    defn1 = CheatCodeDefinition(
        code="DUP-001",
        title="First",
        description="First",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.easy,
        estimated_minutes=15,
        steps=[{"step_number": 1, "title": "S1", "description": "S1", "estimated_minutes": 15}],
    )
    db_session.add(defn1)
    await db_session.flush()

    defn2 = CheatCodeDefinition(
        code="DUP-001",
        title="Second",
        description="Second",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.easy,
        estimated_minutes=15,
        steps=[{"step_number": 1, "title": "S1", "description": "S1", "estimated_minutes": 15}],
    )
    db_session.add(defn2)
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_recommendation_creation(db_session: AsyncSession):
    user = await _create_user(db_session)
    defn = CheatCodeDefinition(
        code="REC-001",
        title="Test Rec CC",
        description="Test",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=10,
        steps=[{"step_number": 1, "title": "S1", "description": "S1", "estimated_minutes": 10}],
    )
    db_session.add(defn)
    await db_session.flush()

    rec = Recommendation(
        user_id=user.id,
        cheat_code_id=defn.id,
        rank=1,
        explanation="You should do this",
        explanation_template="general",
        explanation_inputs={"savings_min": "5", "savings_max": "50"},
        confidence="high",
        is_quick_win=True,
    )
    db_session.add(rec)
    await db_session.flush()

    result = await db_session.execute(
        select(Recommendation).where(Recommendation.user_id == user.id)
    )
    loaded = result.scalar_one()
    assert loaded.rank == 1
    assert loaded.confidence == "high"
    assert loaded.is_quick_win is True


@pytest.mark.asyncio
async def test_cheat_code_run_and_steps(db_session: AsyncSession):
    user = await _create_user(db_session)
    defn = CheatCodeDefinition(
        code="RUN-001",
        title="Run Test CC",
        description="Test",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=10,
        steps=[
            {"step_number": 1, "title": "S1", "description": "S1", "estimated_minutes": 5},
            {"step_number": 2, "title": "S2", "description": "S2", "estimated_minutes": 5},
        ],
    )
    db_session.add(defn)
    await db_session.flush()

    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.in_progress,
        started_at=datetime.now(timezone.utc),
        total_steps=2,
        completed_steps=0,
    )
    db_session.add(run)
    await db_session.flush()

    step1 = StepRun(run_id=run.id, step_number=1, status=RunStatus.not_started)
    step2 = StepRun(run_id=run.id, step_number=2, status=RunStatus.not_started)
    db_session.add_all([step1, step2])
    await db_session.flush()

    # Verify
    result = await db_session.execute(
        select(StepRun).where(StepRun.run_id == run.id).order_by(StepRun.step_number)
    )
    steps = result.scalars().all()
    assert len(steps) == 2
    assert steps[0].step_number == 1
    assert steps[1].step_number == 2
    assert all(s.status == RunStatus.not_started for s in steps)


@pytest.mark.asyncio
async def test_goal_fk_to_user(db_session: AsyncSession):
    """Goal must reference an existing user."""
    goal = Goal(
        user_id=uuid.uuid4(),  # non-existent user
        goal_type=GoalType.save_money,
        title="Should fail",
    )
    db_session.add(goal)
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_recommendation_fk_to_user(db_session: AsyncSession):
    """Recommendation must reference existing user."""
    defn = CheatCodeDefinition(
        code="FK-001",
        title="FK Test",
        description="Test",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.easy,
        estimated_minutes=10,
        steps=[{"step_number": 1, "title": "S1", "description": "S1", "estimated_minutes": 10}],
    )
    db_session.add(defn)
    await db_session.flush()

    rec = Recommendation(
        user_id=uuid.uuid4(),  # non-existent user
        cheat_code_id=defn.id,
        rank=1,
        explanation="test",
        explanation_template="general",
        explanation_inputs={},
        confidence="medium",
    )
    db_session.add(rec)
    with pytest.raises(Exception):
        await db_session.flush()
