"""Phase 7 service tests: lesson seed data."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.lesson_seed import LESSONS, seed_lessons
from app.services import learn_service


@pytest.mark.asyncio
async def test_seed_creates_10_lessons(db_session: AsyncSession):
    """Seed creates exactly 10 lessons."""
    count = await seed_lessons(db_session)
    assert count == 10


@pytest.mark.asyncio
async def test_seed_idempotent(db_session: AsyncSession):
    """Second seed creates 0 new lessons."""
    await seed_lessons(db_session)
    count = await seed_lessons(db_session)
    assert count == 0


@pytest.mark.asyncio
async def test_seed_all_active(db_session: AsyncSession):
    """All seeded lessons are active."""
    await seed_lessons(db_session)
    lessons = await learn_service.get_lessons(db_session)
    assert len(lessons) == 10
    assert all(l.is_active for l in lessons)


@pytest.mark.asyncio
async def test_seed_categories_coverage(db_session: AsyncSession):
    """Seed covers all 5 categories with 2 each."""
    await seed_lessons(db_session)
    lessons = await learn_service.get_lessons(db_session)
    categories = {}
    for l in lessons:
        cat = l.category.value if hasattr(l.category, 'value') else l.category
        categories[cat] = categories.get(cat, 0) + 1
    assert len(categories) == 5
    assert all(v == 2 for v in categories.values())


@pytest.mark.asyncio
async def test_seed_sections_count(db_session: AsyncSession):
    """Each lesson has sections matching total_sections."""
    await seed_lessons(db_session)
    lessons = await learn_service.get_lessons(db_session)
    for l in lessons:
        assert len(l.sections) == l.total_sections
        assert l.total_sections >= 2


@pytest.mark.asyncio
async def test_seed_data_matches_constant():
    """LESSONS constant has exactly 10 entries with required fields."""
    assert len(LESSONS) == 10
    for lesson in LESSONS:
        assert "code" in lesson
        assert "title" in lesson
        assert "description" in lesson
        assert "category" in lesson
        assert "sections" in lesson
        assert "estimated_minutes" in lesson
        for section in lesson["sections"]:
            assert "section_number" in section
            assert "title" in section
            assert "content" in section
            assert "key_takeaway" in section
