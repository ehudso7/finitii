"""Goal routes: create, list, deactivate goals; create, list, delete constraints."""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.goal import GoalPriority, GoalType
from app.models.user import User
from app.schemas.goal import ConstraintCreate, ConstraintRead, GoalCreate, GoalRead
from app.services import goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


def _parse_goal_type(value: str) -> GoalType:
    try:
        return GoalType(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid goal_type: {value}",
        )


def _parse_priority(value: str) -> GoalPriority:
    try:
        return GoalPriority(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {value}",
        )


@router.post("", status_code=201, response_model=GoalRead)
async def create_goal(
    body: GoalCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    goal_type = _parse_goal_type(body.goal_type)
    priority = _parse_priority(body.priority)

    goal = await goal_service.create_goal(
        db,
        user_id=current_user.id,
        goal_type=goal_type,
        title=body.title,
        description=body.description,
        target_amount=body.target_amount,
        priority=priority,
        target_date=body.target_date,
        ip_address=ip,
    )
    return goal


@router.get("", response_model=list[GoalRead])
async def list_goals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await goal_service.get_goals(db, current_user.id)


@router.delete("/{goal_id}")
async def deactivate_goal(
    goal_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    try:
        gid = uuid_mod.UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal_id")

    await goal_service.deactivate_goal(
        db, goal_id=gid, user_id=current_user.id, ip_address=ip
    )
    return {"status": "deactivated"}


# ── Constraints ──


@router.post("/constraints", status_code=201, response_model=ConstraintRead)
async def create_constraint(
    body: ConstraintCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    constraint = await goal_service.create_constraint(
        db,
        user_id=current_user.id,
        constraint_type=body.constraint_type,
        label=body.label,
        amount=body.amount,
        notes=body.notes,
        ip_address=ip,
    )
    return constraint


@router.get("/constraints", response_model=list[ConstraintRead])
async def list_constraints(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await goal_service.get_constraints(db, current_user.id)


@router.delete("/constraints/{constraint_id}")
async def delete_constraint(
    constraint_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    try:
        cid = uuid_mod.UUID(constraint_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid constraint_id")

    await goal_service.delete_constraint(
        db, constraint_id=cid, user_id=current_user.id, ip_address=ip
    )
    return {"status": "deleted"}
