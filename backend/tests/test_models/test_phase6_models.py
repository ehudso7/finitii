"""Phase 6 model tests: CoachMemory model."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_memory import CoachAggressiveness, CoachMemory, CoachTone
from app.models.user import User


@pytest.mark.asyncio
async def test_coach_memory_create(db_session: AsyncSession):
    """CoachMemory row can be created with defaults."""
    user = User(email="cm@test.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    mem = CoachMemory(user_id=user.id)
    db_session.add(mem)
    await db_session.flush()

    assert mem.id is not None
    assert mem.tone == CoachTone.neutral
    assert mem.aggressiveness == CoachAggressiveness.moderate


@pytest.mark.asyncio
async def test_coach_memory_custom_values(db_session: AsyncSession):
    """CoachMemory stores custom tone and aggressiveness."""
    user = User(email="cm2@test.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    mem = CoachMemory(
        user_id=user.id,
        tone=CoachTone.encouraging,
        aggressiveness=CoachAggressiveness.aggressive,
    )
    db_session.add(mem)
    await db_session.flush()

    assert mem.tone == CoachTone.encouraging
    assert mem.aggressiveness == CoachAggressiveness.aggressive


@pytest.mark.asyncio
async def test_coach_memory_unique_per_user(db_session: AsyncSession):
    """Only one CoachMemory row per user (unique constraint)."""
    user = User(email="cm3@test.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    mem1 = CoachMemory(user_id=user.id)
    db_session.add(mem1)
    await db_session.flush()

    mem2 = CoachMemory(user_id=user.id)
    db_session.add(mem2)
    with pytest.raises(Exception):  # IntegrityError
        await db_session.flush()


@pytest.mark.asyncio
async def test_coach_tone_enum_values():
    """CoachTone enum has the expected values."""
    assert set(CoachTone) == {
        CoachTone.encouraging,
        CoachTone.direct,
        CoachTone.neutral,
    }


@pytest.mark.asyncio
async def test_coach_aggressiveness_enum_values():
    """CoachAggressiveness enum has the expected values."""
    assert set(CoachAggressiveness) == {
        CoachAggressiveness.conservative,
        CoachAggressiveness.moderate,
        CoachAggressiveness.aggressive,
    }
