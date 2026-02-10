"""Coach routes: explain, execute, plan, review, recap, and memory management.

Phase 2: explain + execute
Phase 6: plan, review, recap + coach memory (requires ai_memory consent)
"""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.coach_memory import CoachAggressiveness, CoachTone
from app.models.user import User
from app.schemas.coach import (
    CoachMemoryRead,
    CoachMemoryUpdate,
    CoachRequest,
    CoachResponse,
)
from app.services import coach_memory_service, coach_service

router = APIRouter(prefix="/coach", tags=["coach"])

VALID_MODES = {"explain", "execute", "plan", "review", "recap"}

VALID_TONES = {t.value for t in CoachTone}
VALID_AGGRESSIVENESS = {a.value for a in CoachAggressiveness}


@router.post("", response_model=CoachResponse)
async def coach(
    body: CoachRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Coach endpoint: explain, execute, plan, review, or recap mode."""
    ip = request.client.host if request.client else None

    if body.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Mode must be one of: {', '.join(sorted(VALID_MODES))}.",
        )

    # Explain and execute require context_type and context_id
    if body.mode in ("explain", "execute"):
        if not body.context_type:
            raise HTTPException(
                status_code=400,
                detail="context_type is required for explain/execute mode.",
            )
        if not body.context_id:
            raise HTTPException(
                status_code=400,
                detail="context_id is required for explain/execute mode.",
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
    elif body.mode == "plan":
        result = await coach_service.plan(
            db,
            user_id=current_user.id,
            ip_address=ip,
        )
    elif body.mode == "review":
        result = await coach_service.review(
            db,
            user_id=current_user.id,
            ip_address=ip,
        )
    elif body.mode == "recap":
        result = await coach_service.recap(
            db,
            user_id=current_user.id,
            ip_address=ip,
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported mode.")

    return CoachResponse(**result)


@router.get("/memory", response_model=CoachMemoryRead | None)
async def get_memory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get coach memory preferences. Returns null if no ai_memory consent."""
    memory = await coach_memory_service.get_memory(
        db, user_id=current_user.id
    )
    if memory is None:
        return None
    return CoachMemoryRead.model_validate(memory)


@router.put("/memory", response_model=CoachMemoryRead)
async def update_memory(
    body: CoachMemoryUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set/update coach memory preferences. Requires ai_memory consent."""
    ip = request.client.host if request.client else None

    # Validate tone
    tone = None
    if body.tone is not None:
        if body.tone not in VALID_TONES:
            raise HTTPException(
                status_code=400,
                detail=f"tone must be one of: {', '.join(sorted(VALID_TONES))}",
            )
        tone = CoachTone(body.tone)

    # Validate aggressiveness
    aggressiveness = None
    if body.aggressiveness is not None:
        if body.aggressiveness not in VALID_AGGRESSIVENESS:
            raise HTTPException(
                status_code=400,
                detail=f"aggressiveness must be one of: {', '.join(sorted(VALID_AGGRESSIVENESS))}",
            )
        aggressiveness = CoachAggressiveness(body.aggressiveness)

    try:
        memory = await coach_memory_service.set_memory(
            db,
            user_id=current_user.id,
            tone=tone,
            aggressiveness=aggressiveness,
            ip_address=ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return CoachMemoryRead.model_validate(memory)


@router.delete("/memory", status_code=204)
async def delete_memory(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete coach memory preferences."""
    ip = request.client.host if request.client else None
    await coach_memory_service.delete_memory(
        db, user_id=current_user.id, ip_address=ip
    )
