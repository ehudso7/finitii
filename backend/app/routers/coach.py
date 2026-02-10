"""Coach routes: explain and execute modes only (Phase 2)."""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.coach import CoachRequest, CoachResponse
from app.services import coach_service

router = APIRouter(prefix="/coach", tags=["coach"])


@router.post("", response_model=CoachResponse)
async def coach(
    body: CoachRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Coach endpoint: explain or execute mode."""
    ip = request.client.host if request.client else None

    if body.mode not in ("explain", "execute"):
        raise HTTPException(
            status_code=400,
            detail="Mode must be 'explain' or 'execute'.",
        )

    try:
        context_id = uuid_mod.UUID(body.context_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid context_id")

    if body.mode == "explain":
        result = await coach_service.explain(
            db,
            user_id=current_user.id,
            context_type=body.context_type,
            context_id=context_id,
            question=body.question,
            ip_address=ip,
        )
    else:
        result = await coach_service.execute(
            db,
            user_id=current_user.id,
            context_type=body.context_type,
            context_id=context_id,
            ip_address=ip,
        )

    return CoachResponse(**result)
