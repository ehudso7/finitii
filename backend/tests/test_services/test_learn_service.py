"""Phase 7 service tests: learn service (lessons, progress, completion)."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit import AuditLogEvent
from app.models.learn import (
    LessonCategory,
    LessonDefinition,
    LessonProgress,
    LessonStatus,
)
from app.models.user import User
from app.services import learn_service


async def _create_user(db: AsyncSession, email: str = "learn@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _create_lesson(
    db: AsyncSession,
    code: str = "L-T01",
    category: LessonCategory = LessonCategory.save_money,
    sections: list | None = None,
    is_active: bool = True,
) -> LessonDefinition:
    if sections is None:
        sections = [
            {"section_number": 1, "title": "Sec 1", "content": "C1", "key_takeaway": "T1"},
            {"section_number": 2, "title": "Sec 2", "content": "C2", "key_takeaway": "T2"},
            {"section_number": 3, "title": "Sec 3", "content": "C3", "key_takeaway": "T3"},
        ]
    lesson = LessonDefinition(
        code=code,
        title=f"Lesson {code}",
        description=f"Description for {code}",
        category=category,
        sections=sections,
        total_sections=len(sections),
        estimated_minutes=5,
        display_order=1,
        is_active=is_active,
    )
    db.add(lesson)
    await db.flush()
    return lesson


# --- get_lessons ---

@pytest.mark.asyncio
async def test_get_lessons_all(db_session: AsyncSession):
    """List all active lessons."""
    await _create_lesson(db_session, code="L-A01")
    await _create_lesson(db_session, code="L-A02")
    await _create_lesson(db_session, code="L-INACTIVE", is_active=False)

    lessons = await learn_service.get_lessons(db_session)
    codes = [l.code for l in lessons]
    assert "L-A01" in codes
    assert "L-A02" in codes
    assert "L-INACTIVE" not in codes


@pytest.mark.asyncio
async def test_get_lessons_by_category(db_session: AsyncSession):
    """Filter lessons by category."""
    await _create_lesson(db_session, code="L-SM", category=LessonCategory.save_money)
    await _create_lesson(db_session, code="L-BB", category=LessonCategory.budget_better)

    lessons = await learn_service.get_lessons(db_session, category="save_money")
    assert len(lessons) == 1
    assert lessons[0].code == "L-SM"


# --- get_lesson ---

@pytest.mark.asyncio
async def test_get_lesson_by_id(db_session: AsyncSession):
    """Get a specific lesson."""
    lesson = await _create_lesson(db_session, code="L-GET")
    result = await learn_service.get_lesson(db_session, lesson_id=lesson.id)
    assert result.code == "L-GET"


@pytest.mark.asyncio
async def test_get_lesson_not_found(db_session: AsyncSession):
    """Getting non-existent lesson raises exception."""
    import uuid
    with pytest.raises(Exception):
        await learn_service.get_lesson(db_session, lesson_id=uuid.uuid4())


# --- start_lesson ---

@pytest.mark.asyncio
async def test_start_lesson(db_session: AsyncSession):
    """Start a lesson creates progress record."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-START")

    progress = await learn_service.start_lesson(
        db_session, user_id=user.id, lesson_id=lesson.id
    )
    assert progress.status == LessonStatus.in_progress
    assert progress.completed_sections == 0
    assert progress.started_at is not None


@pytest.mark.asyncio
async def test_start_lesson_idempotent(db_session: AsyncSession):
    """Starting an in-progress lesson returns existing progress."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-IDEM")

    p1 = await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    p2 = await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    assert p1.id == p2.id


@pytest.mark.asyncio
async def test_start_lesson_restart_completed(db_session: AsyncSession):
    """Starting a completed lesson resets progress."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-RESTART")

    progress = await learn_service.start_lesson(
        db_session, user_id=user.id, lesson_id=lesson.id
    )
    # Complete it
    progress.status = LessonStatus.completed
    progress.completed_sections = lesson.total_sections
    progress.completed_at = datetime.now(timezone.utc)
    await db_session.flush()

    restarted = await learn_service.start_lesson(
        db_session, user_id=user.id, lesson_id=lesson.id
    )
    assert restarted.id == progress.id
    assert restarted.status == LessonStatus.in_progress
    assert restarted.completed_sections == 0
    assert restarted.completed_at is None


@pytest.mark.asyncio
async def test_start_lesson_audit_logged(db_session: AsyncSession):
    """Starting a lesson is audit-logged."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-AUDIT")

    await learn_service.start_lesson(
        db_session, user_id=user.id, lesson_id=lesson.id
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "lesson.started",
        )
    )
    event = result.scalar_one()
    assert event.detail["lesson_code"] == "L-AUDIT"


# --- complete_section ---

@pytest.mark.asyncio
async def test_complete_section(db_session: AsyncSession):
    """Completing a section advances progress."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-SEC")

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    progress = await learn_service.complete_section(
        db_session, user_id=user.id, lesson_id=lesson.id, section_number=1
    )
    assert progress.completed_sections == 1
    assert progress.status == LessonStatus.in_progress


@pytest.mark.asyncio
async def test_complete_all_sections_auto_completes(db_session: AsyncSession):
    """Completing all sections auto-completes the lesson."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-AUTO")

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    for i in range(1, lesson.total_sections + 1):
        progress = await learn_service.complete_section(
            db_session, user_id=user.id, lesson_id=lesson.id, section_number=i
        )

    assert progress.status == LessonStatus.completed
    assert progress.completed_at is not None


@pytest.mark.asyncio
async def test_complete_section_invalid_number(db_session: AsyncSession):
    """Invalid section number raises ValueError."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-INV")

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    with pytest.raises(ValueError, match="Invalid section_number"):
        await learn_service.complete_section(
            db_session, user_id=user.id, lesson_id=lesson.id, section_number=99
        )


@pytest.mark.asyncio
async def test_complete_section_zero_invalid(db_session: AsyncSession):
    """Section number 0 is invalid."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-ZERO")

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    with pytest.raises(ValueError, match="Invalid section_number"):
        await learn_service.complete_section(
            db_session, user_id=user.id, lesson_id=lesson.id, section_number=0
        )


@pytest.mark.asyncio
async def test_complete_section_not_started(db_session: AsyncSession):
    """Completing section without starting raises ValueError."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-NOTST")

    with pytest.raises(ValueError, match="not started"):
        await learn_service.complete_section(
            db_session, user_id=user.id, lesson_id=lesson.id, section_number=1
        )


@pytest.mark.asyncio
async def test_complete_section_already_completed(db_session: AsyncSession):
    """Completing section on completed lesson raises ValueError."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-DONE",
        sections=[{"section_number": 1, "title": "S", "content": "C", "key_takeaway": "T"}])

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    await learn_service.complete_section(
        db_session, user_id=user.id, lesson_id=lesson.id, section_number=1
    )
    with pytest.raises(ValueError, match="already completed"):
        await learn_service.complete_section(
            db_session, user_id=user.id, lesson_id=lesson.id, section_number=1
        )


@pytest.mark.asyncio
async def test_complete_section_audit_logged(db_session: AsyncSession):
    """Section completion is audit-logged."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-SAUD")

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    await learn_service.complete_section(
        db_session, user_id=user.id, lesson_id=lesson.id, section_number=1
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "lesson.section_completed",
        )
    )
    event = result.scalar_one()
    assert event.detail["section_number"] == 1
    assert event.detail["lesson_code"] == "L-SAUD"


# --- get_user_progress ---

@pytest.mark.asyncio
async def test_get_user_progress(db_session: AsyncSession):
    """Get all progress for a user."""
    user = await _create_user(db_session)
    l1 = await _create_lesson(db_session, code="L-P1")
    l2 = await _create_lesson(db_session, code="L-P2")

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=l1.id)
    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=l2.id)

    progress = await learn_service.get_user_progress(db_session, user_id=user.id)
    assert len(progress) == 2


@pytest.mark.asyncio
async def test_get_progress_for_lesson(db_session: AsyncSession):
    """Get progress for a specific lesson."""
    user = await _create_user(db_session)
    lesson = await _create_lesson(db_session, code="L-SPEC")

    assert await learn_service.get_progress_for_lesson(
        db_session, user_id=user.id, lesson_id=lesson.id
    ) is None

    await learn_service.start_lesson(db_session, user_id=user.id, lesson_id=lesson.id)
    progress = await learn_service.get_progress_for_lesson(
        db_session, user_id=user.id, lesson_id=lesson.id
    )
    assert progress is not None
    assert progress.lesson_id == lesson.id
