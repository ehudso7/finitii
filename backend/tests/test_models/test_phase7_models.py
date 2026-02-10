"""Phase 7 model tests: LessonDefinition, LessonProgress, ScenarioDefinition, ScenarioRun."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learn import (
    LessonCategory,
    LessonDefinition,
    LessonProgress,
    LessonStatus,
)
from app.models.practice import (
    ScenarioCategory,
    ScenarioDefinition,
    ScenarioRun,
    ScenarioRunStatus,
)
from app.models.user import User


async def _create_user(db: AsyncSession) -> User:
    user = User(email="p7model@test.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_lesson_definition_create(db_session: AsyncSession):
    """LessonDefinition stores all fields correctly."""
    lesson = LessonDefinition(
        code="L-TEST",
        title="Test Lesson",
        description="A test lesson.",
        category=LessonCategory.save_money,
        sections=[
            {"section_number": 1, "title": "Sec1", "content": "Content", "key_takeaway": "Takeaway"},
        ],
        total_sections=1,
        estimated_minutes=5,
        display_order=1,
    )
    db_session.add(lesson)
    await db_session.flush()

    assert lesson.id is not None
    assert lesson.code == "L-TEST"
    assert lesson.category == LessonCategory.save_money
    assert lesson.total_sections == 1
    assert lesson.is_active is True


@pytest.mark.asyncio
async def test_lesson_definition_unique_code(db_session: AsyncSession):
    """LessonDefinition enforces unique code constraint."""
    for i in range(2):
        db_session.add(LessonDefinition(
            code="L-DUP",
            title=f"Lesson {i}",
            description="Test",
            category=LessonCategory.budget_better,
            sections=[],
            total_sections=0,
            estimated_minutes=5,
            display_order=i,
        ))
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_lesson_progress_create(db_session: AsyncSession):
    """LessonProgress tracks user progress through a lesson."""
    user = await _create_user(db_session)
    lesson = LessonDefinition(
        code="L-PROG",
        title="Progress Test",
        description="Test",
        category=LessonCategory.reduce_spending,
        sections=[{"section_number": 1, "title": "S", "content": "C", "key_takeaway": "T"}],
        total_sections=1,
        estimated_minutes=5,
        display_order=1,
    )
    db_session.add(lesson)
    await db_session.flush()

    progress = LessonProgress(
        user_id=user.id,
        lesson_id=lesson.id,
        status=LessonStatus.in_progress,
        completed_sections=0,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(progress)
    await db_session.flush()

    assert progress.id is not None
    assert progress.status == LessonStatus.in_progress
    assert progress.completed_sections == 0


@pytest.mark.asyncio
async def test_scenario_definition_create(db_session: AsyncSession):
    """ScenarioDefinition stores sliders and initial_state."""
    scenario = ScenarioDefinition(
        code="S-TEST",
        title="Test Scenario",
        description="A test scenario.",
        category=ScenarioCategory.pay_off_debt,
        initial_state={"debt": 10000},
        sliders=[{"key": "extra", "label": "Extra", "min": 0, "max": 500, "step": 50, "default": 100}],
        outcome_template="You'd save {extra}.",
        learning_points=["Test point"],
        estimated_minutes=5,
        display_order=1,
    )
    db_session.add(scenario)
    await db_session.flush()

    assert scenario.id is not None
    assert scenario.code == "S-TEST"
    assert scenario.initial_state["debt"] == 10000
    assert len(scenario.sliders) == 1
    assert scenario.is_active is True


@pytest.mark.asyncio
async def test_scenario_run_create(db_session: AsyncSession):
    """ScenarioRun captures slider values with medium confidence cap."""
    user = await _create_user(db_session)
    scenario = ScenarioDefinition(
        code="S-RUN",
        title="Run Test",
        description="Test",
        category=ScenarioCategory.save_money,
        initial_state={"income": 4000},
        sliders=[{"key": "savings", "label": "Savings", "min": 0, "max": 1000, "step": 50, "default": 200}],
        outcome_template="Template",
        learning_points=["Point"],
        estimated_minutes=5,
        display_order=1,
    )
    db_session.add(scenario)
    await db_session.flush()

    run = ScenarioRun(
        user_id=user.id,
        scenario_id=scenario.id,
        slider_values={"savings": 200},
        confidence="medium",
        status=ScenarioRunStatus.in_progress,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()

    assert run.id is not None
    assert run.confidence == "medium"
    assert run.status == ScenarioRunStatus.in_progress
    assert run.plan_generated is False
    assert run.computed_outcome is None


@pytest.mark.asyncio
async def test_scenario_definition_unique_code(db_session: AsyncSession):
    """ScenarioDefinition enforces unique code constraint."""
    for i in range(2):
        db_session.add(ScenarioDefinition(
            code="S-DUP",
            title=f"Scenario {i}",
            description="Test",
            category=ScenarioCategory.budget_better,
            initial_state={},
            sliders=[],
            outcome_template="Template",
            learning_points=[],
            estimated_minutes=5,
            display_order=i,
        ))
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_lesson_category_values():
    """LessonCategory has exactly 5 categories."""
    assert len(LessonCategory) == 5
    assert LessonCategory.save_money.value == "save_money"
    assert LessonCategory.reduce_spending.value == "reduce_spending"
    assert LessonCategory.pay_off_debt.value == "pay_off_debt"
    assert LessonCategory.build_emergency_fund.value == "build_emergency_fund"
    assert LessonCategory.budget_better.value == "budget_better"


@pytest.mark.asyncio
async def test_scenario_category_values():
    """ScenarioCategory has exactly 5 categories matching lesson categories."""
    assert len(ScenarioCategory) == 5
    for cat in ScenarioCategory:
        assert cat.value in [lc.value for lc in LessonCategory]
