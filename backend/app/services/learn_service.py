"""Learn service: lesson listing, progress tracking, completion.

All writes audit-logged.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learn import LessonDefinition, LessonProgress, LessonStatus
from app.services import audit_service


async def get_lessons(
    db: AsyncSession,
    *,
    category: str | None = None,
) -> list[LessonDefinition]:
    """List all active lessons, optionally filtered by category."""
    stmt = (
        select(LessonDefinition)
        .where(LessonDefinition.is_active == True)  # noqa: E712
        .order_by(LessonDefinition.display_order.asc())
    )
    if category:
        stmt = stmt.where(LessonDefinition.category == category)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_lesson(
    db: AsyncSession,
    *,
    lesson_id: uuid.UUID,
) -> LessonDefinition:
    """Get a single lesson by ID."""
    result = await db.execute(
        select(LessonDefinition).where(LessonDefinition.id == lesson_id)
    )
    return result.scalar_one()


async def get_user_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> list[LessonProgress]:
    """Get all lesson progress for a user."""
    result = await db.execute(
        select(LessonProgress)
        .where(LessonProgress.user_id == user_id)
        .order_by(LessonProgress.created_at.asc())
    )
    return list(result.scalars().all())


async def get_progress_for_lesson(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
) -> LessonProgress | None:
    """Get user's progress for a specific lesson."""
    result = await db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_id == lesson_id,
        )
    )
    return result.scalar_one_or_none()


async def start_lesson(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
    ip_address: str | None = None,
) -> LessonProgress:
    """Start a lesson. Creates progress record if not exists."""
    # Verify lesson exists
    lesson = await get_lesson(db, lesson_id=lesson_id)

    # Check for existing progress
    existing = await get_progress_for_lesson(
        db, user_id=user_id, lesson_id=lesson_id
    )
    if existing is not None:
        if existing.status == LessonStatus.completed:
            # Allow restart
            existing.status = LessonStatus.in_progress
            existing.completed_sections = 0
            existing.started_at = datetime.now(timezone.utc)
            existing.completed_at = None
            await db.flush()
            return existing
        return existing  # Already in progress

    progress = LessonProgress(
        user_id=user_id,
        lesson_id=lesson_id,
        status=LessonStatus.in_progress,
        started_at=datetime.now(timezone.utc),
        completed_sections=0,
    )
    db.add(progress)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="lesson.started",
        entity_type="LessonProgress",
        entity_id=progress.id,
        action="start",
        detail={"lesson_code": lesson.code, "lesson_title": lesson.title},
        ip_address=ip_address,
    )

    return progress


async def complete_section(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
    section_number: int,
    ip_address: str | None = None,
) -> LessonProgress:
    """Mark a section as completed. Auto-completes lesson if all sections done."""
    lesson = await get_lesson(db, lesson_id=lesson_id)

    if section_number < 1 or section_number > lesson.total_sections:
        raise ValueError(
            f"Invalid section_number {section_number}. "
            f"Lesson has {lesson.total_sections} sections."
        )

    progress = await get_progress_for_lesson(
        db, user_id=user_id, lesson_id=lesson_id
    )
    if progress is None:
        raise ValueError("Lesson not started. Call start_lesson first.")

    if progress.status == LessonStatus.completed:
        raise ValueError("Lesson already completed.")

    # Advance progress (sections must be completed in order)
    if section_number > progress.completed_sections:
        progress.completed_sections = section_number

    # Auto-complete if all sections done
    if progress.completed_sections >= lesson.total_sections:
        progress.status = LessonStatus.completed
        progress.completed_at = datetime.now(timezone.utc)

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="lesson.section_completed",
        entity_type="LessonProgress",
        entity_id=progress.id,
        action="complete_section",
        detail={
            "lesson_code": lesson.code,
            "section_number": section_number,
            "completed_sections": progress.completed_sections,
            "total_sections": lesson.total_sections,
            "lesson_completed": progress.status == LessonStatus.completed,
        },
        ip_address=ip_address,
    )

    return progress
