"""Onboarding routes: get state, advance step."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.onboarding import OnboardingStep
from app.models.user import User
from app.schemas.onboarding import OnboardingStateRead
from app.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/state", response_model=OnboardingStateRead)
async def get_state(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state = await onboarding_service.get_state(db, current_user.id)
    return state


@router.post("/advance")
async def advance(
    request: Request,
    step: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Advance onboarding by completing the given step."""
    ip = request.client.host if request.client else None

    try:
        onboarding_step = OnboardingStep(step)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step: {step}. Must be one of: {[s.value for s in OnboardingStep]}",
        )

    try:
        state = await onboarding_service.advance_step(
            db,
            user_id=current_user.id,
            completed_step=onboarding_step,
            ip_address=ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "current_step": state.current_step.value,
        "completed": state.current_step == OnboardingStep.completed,
    }
