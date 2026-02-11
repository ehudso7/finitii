"""Phase 7 service tests: practice service (scenarios, simulation, AAR, turn-into-plan)."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit import AuditLogEvent
from app.models.practice import (
    ScenarioCategory,
    ScenarioDefinition,
    ScenarioRun,
    ScenarioRunStatus,
)
from app.models.user import User
from app.services import practice_service


async def _create_user(db: AsyncSession, email: str = "practice@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _create_scenario(
    db: AsyncSession,
    code: str = "S-T01",
    category: ScenarioCategory = ScenarioCategory.save_money,
) -> ScenarioDefinition:
    """Create S-001-like scenario for testing."""
    scenario = ScenarioDefinition(
        code=code,
        title=f"Scenario {code}",
        description=f"Test scenario {code}",
        category=category,
        initial_state={
            "monthly_income": 4000,
            "monthly_expenses": 3200,
            "current_savings": 500,
            "goal_amount": 5000,
        },
        sliders=[
            {"key": "monthly_savings", "label": "Monthly Savings ($)", "min": 50, "max": 800, "step": 50, "default": 200},
            {"key": "expense_reduction", "label": "Expense Reduction ($)", "min": 0, "max": 500, "step": 25, "default": 0},
        ],
        outcome_template="Template {monthly_savings}",
        learning_points=["Point 1", "Point 2"],
        estimated_minutes=5,
        display_order=1,
    )
    db.add(scenario)
    await db.flush()
    return scenario


# --- get_scenarios ---

@pytest.mark.asyncio
async def test_get_scenarios_all(db_session: AsyncSession):
    """List all active scenarios."""
    await _create_scenario(db_session, code="S-A01")
    await _create_scenario(db_session, code="S-A02")

    # Inactive one
    inactive = ScenarioDefinition(
        code="S-OFF", title="Off", description="Off",
        category=ScenarioCategory.budget_better,
        initial_state={}, sliders=[], outcome_template="T",
        learning_points=[], estimated_minutes=5, display_order=99,
        is_active=False,
    )
    db_session.add(inactive)
    await db_session.flush()

    scenarios = await practice_service.get_scenarios(db_session)
    codes = [s.code for s in scenarios]
    assert "S-A01" in codes
    assert "S-A02" in codes
    assert "S-OFF" not in codes


@pytest.mark.asyncio
async def test_get_scenarios_by_category(db_session: AsyncSession):
    """Filter scenarios by category."""
    await _create_scenario(db_session, code="S-SM", category=ScenarioCategory.save_money)
    await _create_scenario(db_session, code="S-BB", category=ScenarioCategory.budget_better)

    scenarios = await practice_service.get_scenarios(db_session, category="save_money")
    assert len(scenarios) == 1
    assert scenarios[0].code == "S-SM"


# --- start_scenario ---

@pytest.mark.asyncio
async def test_start_scenario(db_session: AsyncSession):
    """Start a scenario creates run with default slider values."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-START")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    assert run.status == ScenarioRunStatus.in_progress
    assert run.confidence == "medium"
    assert run.slider_values["monthly_savings"] == 200
    assert run.slider_values["expense_reduction"] == 0
    assert run.computed_outcome is None
    assert run.plan_generated is False


@pytest.mark.asyncio
async def test_start_scenario_multiple_runs(db_session: AsyncSession):
    """Multiple runs per scenario allowed."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-MULTI")

    r1 = await practice_service.start_scenario(db_session, user_id=user.id, scenario_id=scenario.id)
    r2 = await practice_service.start_scenario(db_session, user_id=user.id, scenario_id=scenario.id)
    assert r1.id != r2.id


@pytest.mark.asyncio
async def test_start_scenario_audit_logged(db_session: AsyncSession):
    """Starting a scenario is audit-logged."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-SAUD")

    await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "practice.started",
        )
    )
    event = result.scalar_one()
    assert event.detail["scenario_code"] == "S-SAUD"


# --- simulate ---

@pytest.mark.asyncio
async def test_simulate_s001(db_session: AsyncSession):
    """Simulate S-001 (Savings Rate) produces correct outcome."""
    user = await _create_user(db_session)
    # Use actual S-001 scenario structure
    scenario = ScenarioDefinition(
        code="S-001",
        title="Savings Rate Simulator",
        description="Test",
        category=ScenarioCategory.save_money,
        initial_state={
            "monthly_income": 4000,
            "monthly_expenses": 3200,
            "current_savings": 500,
            "goal_amount": 5000,
        },
        sliders=[
            {"key": "monthly_savings", "label": "Monthly Savings ($)", "min": 50, "max": 800, "step": 50, "default": 200},
            {"key": "expense_reduction", "label": "Expense Reduction ($)", "min": 0, "max": 500, "step": 25, "default": 0},
        ],
        outcome_template="Template",
        learning_points=["Point"],
        estimated_minutes=5,
        display_order=1,
    )
    db_session.add(scenario)
    await db_session.flush()

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )

    run = await practice_service.simulate(
        db_session,
        user_id=user.id,
        run_id=run.id,
        slider_values={"monthly_savings": 400, "expense_reduction": 100},
    )

    assert run.computed_outcome is not None
    assert run.computed_outcome["monthly_savings"] == 400
    assert run.computed_outcome["expense_reduction"] == 100
    assert run.computed_outcome["total_monthly"] == 500
    assert run.computed_outcome["total_annual"] == 6000
    assert run.confidence == "medium"


@pytest.mark.asyncio
async def test_simulate_slider_clamping(db_session: AsyncSession):
    """Slider values are clamped to min/max range."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-CLAMP")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )

    # Pass values outside range
    run = await practice_service.simulate(
        db_session,
        user_id=user.id,
        run_id=run.id,
        slider_values={"monthly_savings": 9999, "expense_reduction": -100},
    )

    # monthly_savings clamped to max 800, expense_reduction clamped to min 0
    assert run.slider_values["monthly_savings"] == 800
    assert run.slider_values["expense_reduction"] == 0


@pytest.mark.asyncio
async def test_simulate_completed_run_rejected(db_session: AsyncSession):
    """Cannot simulate on completed run."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-COMPR")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )
    await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )

    with pytest.raises(ValueError, match="already completed"):
        await practice_service.simulate(
            db_session, user_id=user.id, run_id=run.id,
            slider_values={"monthly_savings": 300, "expense_reduction": 50},
        )


@pytest.mark.asyncio
async def test_simulate_audit_logged(db_session: AsyncSession):
    """Simulation is audit-logged with confidence."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-SIMAUD")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "practice.simulated",
        )
    )
    event = result.scalar_one()
    assert event.detail["confidence"] == "medium"


@pytest.mark.asyncio
async def test_confidence_always_medium(db_session: AsyncSession):
    """Confidence is ALWAYS medium (PRD cap)."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-CONF")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    assert run.confidence == "medium"

    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )
    assert run.confidence == "medium"

    run = await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )
    assert run.confidence == "medium"


# --- complete_scenario ---

@pytest.mark.asyncio
async def test_complete_scenario_generates_aar(db_session: AsyncSession):
    """Completing scenario generates After-Action Review."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-AAR")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 400, "expense_reduction": 100},
    )
    run = await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )

    assert run.status == ScenarioRunStatus.completed
    assert run.completed_at is not None
    assert run.after_action_review is not None
    assert "summary" in run.after_action_review
    assert "what_worked" in run.after_action_review
    assert "improvement" in run.after_action_review
    assert "learning_points" in run.after_action_review
    assert run.after_action_review["confidence"] == "medium"


@pytest.mark.asyncio
async def test_complete_without_simulation_rejected(db_session: AsyncSession):
    """Cannot complete without running simulation first."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-NOSIM")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    with pytest.raises(ValueError, match="Must run simulation"):
        await practice_service.complete_scenario(
            db_session, user_id=user.id, run_id=run.id
        )


@pytest.mark.asyncio
async def test_complete_already_completed_rejected(db_session: AsyncSession):
    """Cannot complete already completed scenario."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-DCOMP")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )
    await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )

    with pytest.raises(ValueError, match="already completed"):
        await practice_service.complete_scenario(
            db_session, user_id=user.id, run_id=run.id
        )


@pytest.mark.asyncio
async def test_complete_audit_logged(db_session: AsyncSession):
    """Completion is audit-logged."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-CAUD")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )
    await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "practice.completed",
        )
    )
    event = result.scalar_one()
    assert event.detail["has_aar"] is True
    assert event.detail["confidence"] == "medium"


# --- turn_into_plan ---

@pytest.mark.asyncio
async def test_turn_into_plan(db_session: AsyncSession):
    """Turn into plan creates 3 steps with practice source."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-PLAN")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 400, "expense_reduction": 100},
    )
    run = await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )

    plan = await practice_service.turn_into_plan(
        db_session, user_id=user.id, run_id=run.id
    )

    assert plan["source"] == "practice"
    assert plan["confidence"] == "medium"
    assert len(plan["steps"]) == 3
    assert plan["steps"][0]["action"] == "apply_learning"
    assert plan["steps"][1]["action"] == "category_specific"
    assert plan["steps"][2]["action"] == "validate_with_data"
    assert len(plan["caveats"]) == 3
    assert any("Top 3" in c for c in plan["caveats"])


@pytest.mark.asyncio
async def test_turn_into_plan_marks_generated(db_session: AsyncSession):
    """Turn into plan sets plan_generated flag."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-PGEN")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    assert run.plan_generated is False

    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )
    run = await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )
    await practice_service.turn_into_plan(
        db_session, user_id=user.id, run_id=run.id
    )

    updated = await practice_service.get_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert updated.plan_generated is True


@pytest.mark.asyncio
async def test_turn_into_plan_requires_completed(db_session: AsyncSession):
    """Cannot turn into plan if scenario not completed."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-NCOMP")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )

    with pytest.raises(ValueError, match="Must complete scenario"):
        await practice_service.turn_into_plan(
            db_session, user_id=user.id, run_id=run.id
        )


@pytest.mark.asyncio
async def test_turn_into_plan_audit_logged(db_session: AsyncSession):
    """Turn into plan is audit-logged."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-TAUD")

    run = await practice_service.start_scenario(
        db_session, user_id=user.id, scenario_id=scenario.id
    )
    run = await practice_service.simulate(
        db_session, user_id=user.id, run_id=run.id,
        slider_values={"monthly_savings": 200, "expense_reduction": 0},
    )
    run = await practice_service.complete_scenario(
        db_session, user_id=user.id, run_id=run.id
    )
    await practice_service.turn_into_plan(
        db_session, user_id=user.id, run_id=run.id
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "practice.plan_generated",
        )
    )
    event = result.scalar_one()
    assert event.detail["step_count"] == 3
    assert event.detail["confidence"] == "medium"


# --- get_user_runs / get_run ---

@pytest.mark.asyncio
async def test_get_user_runs(db_session: AsyncSession):
    """Get all runs for a user."""
    user = await _create_user(db_session)
    scenario = await _create_scenario(db_session, code="S-RUNS")

    await practice_service.start_scenario(db_session, user_id=user.id, scenario_id=scenario.id)
    await practice_service.start_scenario(db_session, user_id=user.id, scenario_id=scenario.id)

    runs = await practice_service.get_user_runs(db_session, user_id=user.id)
    assert len(runs) == 2


@pytest.mark.asyncio
async def test_get_user_runs_filter_by_scenario(db_session: AsyncSession):
    """Filter runs by scenario."""
    user = await _create_user(db_session)
    s1 = await _create_scenario(db_session, code="S-F1")
    s2 = await _create_scenario(db_session, code="S-F2")

    await practice_service.start_scenario(db_session, user_id=user.id, scenario_id=s1.id)
    await practice_service.start_scenario(db_session, user_id=user.id, scenario_id=s2.id)

    runs = await practice_service.get_user_runs(
        db_session, user_id=user.id, scenario_id=s1.id
    )
    assert len(runs) == 1
