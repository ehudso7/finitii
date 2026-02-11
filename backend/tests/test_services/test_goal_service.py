"""Goal service tests."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import GoalPriority, GoalType
from app.models.user import User
from app.services import goal_service


async def _create_user(db: AsyncSession) -> User:
    user = User(email="goal@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_create_goal(db_session: AsyncSession):
    user = await _create_user(db_session)
    goal = await goal_service.create_goal(
        db_session,
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Emergency Fund",
        target_amount=Decimal("1000.00"),
        priority=GoalPriority.high,
    )
    assert goal.title == "Emergency Fund"
    assert goal.goal_type == GoalType.save_money
    assert goal.priority == GoalPriority.high
    assert goal.is_active is True
    assert goal.current_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_get_goals(db_session: AsyncSession):
    user = await _create_user(db_session)
    await goal_service.create_goal(
        db_session,
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Goal 1",
    )
    await goal_service.create_goal(
        db_session,
        user_id=user.id,
        goal_type=GoalType.reduce_spending,
        title="Goal 2",
    )
    goals = await goal_service.get_goals(db_session, user.id)
    assert len(goals) == 2


@pytest.mark.asyncio
async def test_deactivate_goal(db_session: AsyncSession):
    user = await _create_user(db_session)
    goal = await goal_service.create_goal(
        db_session,
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Deactivate me",
    )
    deactivated = await goal_service.deactivate_goal(
        db_session, goal_id=goal.id, user_id=user.id
    )
    assert deactivated.is_active is False

    # Active-only query should return empty
    goals = await goal_service.get_goals(db_session, user.id, active_only=True)
    assert len(goals) == 0


@pytest.mark.asyncio
async def test_create_constraint(db_session: AsyncSession):
    user = await _create_user(db_session)
    constraint = await goal_service.create_constraint(
        db_session,
        user_id=user.id,
        constraint_type="monthly_income",
        label="Salary",
        amount=Decimal("5000.00"),
    )
    assert constraint.constraint_type == "monthly_income"
    assert constraint.amount == Decimal("5000.00")


@pytest.mark.asyncio
async def test_get_constraints(db_session: AsyncSession):
    user = await _create_user(db_session)
    await goal_service.create_constraint(
        db_session,
        user_id=user.id,
        constraint_type="monthly_income",
        label="Salary",
        amount=Decimal("5000.00"),
    )
    await goal_service.create_constraint(
        db_session,
        user_id=user.id,
        constraint_type="fixed_expense",
        label="Rent",
        amount=Decimal("1500.00"),
    )
    constraints = await goal_service.get_constraints(db_session, user.id)
    assert len(constraints) == 2


@pytest.mark.asyncio
async def test_delete_constraint(db_session: AsyncSession):
    user = await _create_user(db_session)
    constraint = await goal_service.create_constraint(
        db_session,
        user_id=user.id,
        constraint_type="monthly_income",
        label="Salary",
        amount=Decimal("5000.00"),
    )
    await goal_service.delete_constraint(
        db_session, constraint_id=constraint.id, user_id=user.id
    )
    constraints = await goal_service.get_constraints(db_session, user.id)
    assert len(constraints) == 0


@pytest.mark.asyncio
async def test_goal_creation_audit_logged(db_session: AsyncSession):
    """Goal creation must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    await goal_service.create_goal(
        db_session,
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Audited Goal",
    )
    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "goal.created",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].detail["title"] == "Audited Goal"
