"""Cheat code seed tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeDefinition, CheatCodeDifficulty
from app.services.cheat_code_seed import seed_cheat_codes


@pytest.mark.asyncio
async def test_seed_creates_cheat_codes(db_session: AsyncSession):
    definitions = await seed_cheat_codes(db_session)
    assert len(definitions) == 5

    # Verify all are in DB
    result = await db_session.execute(select(CheatCodeDefinition))
    all_defs = result.scalars().all()
    assert len(all_defs) == 5


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session: AsyncSession):
    await seed_cheat_codes(db_session)
    await seed_cheat_codes(db_session)

    result = await db_session.execute(select(CheatCodeDefinition))
    all_defs = result.scalars().all()
    assert len(all_defs) == 5  # Still 5, not 10


@pytest.mark.asyncio
async def test_seed_includes_quick_win(db_session: AsyncSession):
    """At least one quick win (≤10 min) must exist for First Win support."""
    definitions = await seed_cheat_codes(db_session)
    quick_wins = [d for d in definitions if d.difficulty == CheatCodeDifficulty.quick_win]
    assert len(quick_wins) >= 1

    # Quick wins must have estimated_minutes ≤ 10
    for qw in quick_wins:
        assert qw.estimated_minutes <= 10


@pytest.mark.asyncio
async def test_seed_all_have_steps(db_session: AsyncSession):
    """Every cheat code must have at least 1 step."""
    definitions = await seed_cheat_codes(db_session)
    for d in definitions:
        assert isinstance(d.steps, list)
        assert len(d.steps) >= 1
        for step in d.steps:
            assert "step_number" in step
            assert "title" in step
            assert "description" in step
