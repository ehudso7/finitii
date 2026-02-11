"""Phase 7 service tests: scenario seed data."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scenario_seed import SCENARIOS, seed_scenarios
from app.services import practice_service


@pytest.mark.asyncio
async def test_seed_creates_10_scenarios(db_session: AsyncSession):
    """Seed creates exactly 10 scenarios."""
    count = await seed_scenarios(db_session)
    assert count == 10


@pytest.mark.asyncio
async def test_seed_idempotent(db_session: AsyncSession):
    """Second seed creates 0 new scenarios."""
    await seed_scenarios(db_session)
    count = await seed_scenarios(db_session)
    assert count == 0


@pytest.mark.asyncio
async def test_seed_all_active(db_session: AsyncSession):
    """All seeded scenarios are active."""
    await seed_scenarios(db_session)
    scenarios = await practice_service.get_scenarios(db_session)
    assert len(scenarios) == 10
    assert all(s.is_active for s in scenarios)


@pytest.mark.asyncio
async def test_seed_categories_coverage(db_session: AsyncSession):
    """Seed covers all 5 categories with 2 each."""
    await seed_scenarios(db_session)
    scenarios = await practice_service.get_scenarios(db_session)
    categories = {}
    for s in scenarios:
        cat = s.category.value if hasattr(s.category, 'value') else s.category
        categories[cat] = categories.get(cat, 0) + 1
    assert len(categories) == 5
    assert all(v == 2 for v in categories.values())


@pytest.mark.asyncio
async def test_seed_sliders_valid(db_session: AsyncSession):
    """Each scenario has at least 1 slider with required fields."""
    await seed_scenarios(db_session)
    scenarios = await practice_service.get_scenarios(db_session)
    for s in scenarios:
        assert len(s.sliders) >= 1
        for slider in s.sliders:
            assert "key" in slider
            assert "label" in slider
            assert "min" in slider
            assert "max" in slider
            assert "step" in slider
            assert "default" in slider
            assert slider["min"] <= slider["default"] <= slider["max"]
            assert slider["step"] > 0


@pytest.mark.asyncio
async def test_seed_initial_state_present(db_session: AsyncSession):
    """Each scenario has initial_state with at least 1 key."""
    await seed_scenarios(db_session)
    scenarios = await practice_service.get_scenarios(db_session)
    for s in scenarios:
        assert isinstance(s.initial_state, dict)
        assert len(s.initial_state) >= 1


@pytest.mark.asyncio
async def test_seed_data_matches_constant():
    """SCENARIOS constant has exactly 10 entries with required fields."""
    assert len(SCENARIOS) == 10
    for scenario in SCENARIOS:
        assert "code" in scenario
        assert "title" in scenario
        assert "initial_state" in scenario
        assert "sliders" in scenario
        assert "outcome_template" in scenario
        assert "learning_points" in scenario
        assert len(scenario["learning_points"]) >= 1
