"""Goal service: create/manage goals and constraints.

All writes audit-logged.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal, GoalPriority, GoalType, UserConstraint
from app.services import audit_service


async def create_goal(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    goal_type: GoalType,
    title: str,
    description: str | None = None,
    target_amount: Decimal | None = None,
    priority: GoalPriority = GoalPriority.medium,
    target_date=None,
    ip_address: str | None = None,
) -> Goal:
    """Create a new financial goal for a user."""
    goal = Goal(
        user_id=user_id,
        goal_type=goal_type,
        title=title,
        description=description,
        target_amount=target_amount,
        priority=priority,
        target_date=target_date,
    )
    db.add(goal)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="goal.created",
        entity_type="Goal",
        entity_id=goal.id,
        action="create",
        detail={
            "goal_type": goal_type.value,
            "title": title,
            "priority": priority.value,
            "target_amount": str(target_amount) if target_amount else None,
        },
        ip_address=ip_address,
    )

    return goal


async def get_goals(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    active_only: bool = True,
) -> list[Goal]:
    """List goals for a user."""
    stmt = select(Goal).where(Goal.user_id == user_id)
    if active_only:
        stmt = stmt.where(Goal.is_active == True)  # noqa: E712
    stmt = stmt.order_by(Goal.created_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def deactivate_goal(
    db: AsyncSession,
    *,
    goal_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> Goal:
    """Deactivate (soft-delete) a goal."""
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    goal = result.scalar_one()
    goal.is_active = False
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="goal.deactivated",
        entity_type="Goal",
        entity_id=goal.id,
        action="deactivate",
        ip_address=ip_address,
    )

    return goal


async def create_constraint(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    constraint_type: str,
    label: str,
    amount: Decimal | None = None,
    notes: str | None = None,
    ip_address: str | None = None,
) -> UserConstraint:
    """Create a user financial constraint."""
    constraint = UserConstraint(
        user_id=user_id,
        constraint_type=constraint_type,
        label=label,
        amount=amount,
        notes=notes,
    )
    db.add(constraint)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="constraint.created",
        entity_type="UserConstraint",
        entity_id=constraint.id,
        action="create",
        detail={
            "constraint_type": constraint_type,
            "label": label,
            "amount": str(amount) if amount else None,
        },
        ip_address=ip_address,
    )

    return constraint


async def get_constraints(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[UserConstraint]:
    """List all constraints for a user."""
    result = await db.execute(
        select(UserConstraint)
        .where(UserConstraint.user_id == user_id)
        .order_by(UserConstraint.created_at.asc())
    )
    return list(result.scalars().all())


async def delete_constraint(
    db: AsyncSession,
    *,
    constraint_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> None:
    """Delete a user constraint."""
    result = await db.execute(
        select(UserConstraint).where(
            UserConstraint.id == constraint_id,
            UserConstraint.user_id == user_id,
        )
    )
    constraint = result.scalar_one()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="constraint.deleted",
        entity_type="UserConstraint",
        entity_id=constraint.id,
        action="delete",
        ip_address=ip_address,
    )

    await db.delete(constraint)
    await db.flush()
