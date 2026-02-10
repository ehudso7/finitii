"""Learn routes: lesson listing, progress tracking, section completion.

Phase 7: Learn + Practice
"""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.learn import (
    CompleteSectionRequest,
    LessonProgressRead,
    LessonRead,
    StartLessonRequest,
)
from app.services import learn_service

router = APIRouter(prefix="/learn", tags=["learn"])


@router.get("/lessons", response_model=list[LessonRead])
async def list_lessons(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all active lessons, optionally filtered by category."""
    lessons = await learn_service.get_lessons(db, category=category)
    return [LessonRead.model_validate(l) for l in lessons]


@router.get("/lessons/{lesson_id}", response_model=LessonRead)
async def get_lesson(
    lesson_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific lesson by ID."""
    try:
        lid = uuid_mod.UUID(lesson_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lesson_id")
    try:
        lesson = await learn_service.get_lesson(db, lesson_id=lid)
    except Exception:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return LessonRead.model_validate(lesson)


@router.get("/progress", response_model=list[LessonProgressRead])
async def list_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all lesson progress for the current user."""
    progress = await learn_service.get_user_progress(db, user_id=current_user.id)
    return [LessonProgressRead.model_validate(p) for p in progress]


@router.get("/progress/{lesson_id}", response_model=LessonProgressRead | None)
async def get_progress_for_lesson(
    lesson_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get progress for a specific lesson."""
    try:
        lid = uuid_mod.UUID(lesson_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lesson_id")
    progress = await learn_service.get_progress_for_lesson(
        db, user_id=current_user.id, lesson_id=lid
    )
    if progress is None:
        return None
    return LessonProgressRead.model_validate(progress)


@router.post("/start", response_model=LessonProgressRead)
async def start_lesson(
    body: StartLessonRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a lesson. Allows restarting completed lessons."""
    ip = request.client.host if request.client else None
    try:
        lid = uuid_mod.UUID(body.lesson_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lesson_id")
    try:
        progress = await learn_service.start_lesson(
            db, user_id=current_user.id, lesson_id=lid, ip_address=ip
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return LessonProgressRead.model_validate(progress)


@router.post("/complete-section", response_model=LessonProgressRead)
async def complete_section(
    body: CompleteSectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a section as completed. Auto-completes lesson if all sections done."""
    ip = request.client.host if request.client else None
    try:
        lid = uuid_mod.UUID(body.lesson_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lesson_id")
    try:
        progress = await learn_service.complete_section(
            db,
            user_id=current_user.id,
            lesson_id=lid,
            section_number=body.section_number,
            ip_address=ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return LessonProgressRead.model_validate(progress)
