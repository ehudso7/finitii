"""Phase 6 service tests: coach plan mode."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeCategory,
    CheatCodeRun,
    Recommendation,
    RunStatus,
)
from app.models.consent import ConsentRecord, ConsentType
from app.models.coach_memory import CoachTone, CoachAggressiveness
from app.models.goal import Goal, GoalType, GoalPriority
from app.models.recurring import Frequency, Confidence, RecurringPattern
from app.models.user import User
from app.services import coach_service, coach_memory_service


async def _create_user(db: AsyncSession, email: str = "plan@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _create_goal(db: AsyncSession, user_id, title: str = "Save $1000") -> Goal:
    goal = Goal(
        user_id=user_id,
        goal_type=GoalType.save_money,
        title=title,
        priority=GoalPriority.high,
    )
    db.add(goal)
    await db.flush()
    return goal


async def _create_definition(db: AsyncSession, code: str = "CC-TEST", **kwargs) -> CheatCodeDefinition:
    defn = CheatCodeDefinition(
        code=code,
        title=kwargs.get("title", "Test Cheat Code"),
        description=kwargs.get("description", "A test code"),
        category=kwargs.get("category", CheatCodeCategory.save_money),
        difficulty=kwargs.get("difficulty", CheatCodeDifficulty.quick_win),
        estimated_minutes=kwargs.get("estimated_minutes", 10),
        steps=[{"step_number": 1, "title": "Step 1", "description": "Do it", "estimated_minutes": 5}],
        potential_savings_min=Decimal("10.00"),
        potential_savings_max=Decimal("50.00"),
    )
    db.add(defn)
    await db.flush()
    return defn


async def _create_recommendation(
    db: AsyncSession, user_id, cheat_code_id, rank: int = 1
) -> Recommendation:
    rec = Recommendation(
        user_id=user_id,
        cheat_code_id=cheat_code_id,
        rank=rank,
        explanation="Test explanation",
        explanation_template="general",
        explanation_inputs={"savings_min": "10", "savings_max": "50"},
        confidence="high",
        is_quick_win=True,
    )
    db.add(rec)
    await db.flush()
    return rec


# --- Plan mode ---

@pytest.mark.asyncio
async def test_plan_empty_context(db_session: AsyncSession):
    """Plan with no data returns empty plan with caveat."""
    user = await _create_user(db_session)
    result = await coach_service.plan(db_session, user_id=user.id)

    assert result["mode"] == "plan"
    assert result["template_used"] == "general"
    assert result["steps"] == [] or any(s["action"] == "set_goal" for s in result["steps"])
    assert "response" in result


@pytest.mark.asyncio
async def test_plan_max_3_steps(db_session: AsyncSession):
    """Plan never returns more than 3 steps."""
    user = await _create_user(db_session)
    await _create_goal(db_session, user.id)

    # Create 5 recommendations
    for i in range(5):
        defn = await _create_definition(db_session, code=f"CC-P{i}")
        await _create_recommendation(db_session, user.id, defn.id, rank=i + 1)

    result = await coach_service.plan(db_session, user_id=user.id)
    assert len(result["steps"]) <= 3


@pytest.mark.asyncio
async def test_plan_includes_recommendations(db_session: AsyncSession):
    """Plan includes steps for top recommendations."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session, code="CC-R1", title="Cancel Streaming")
    await _create_recommendation(db_session, user.id, defn.id, rank=1)

    result = await coach_service.plan(db_session, user_id=user.id)
    actions = [s["action"] for s in result["steps"]]
    assert "start_recommendation" in actions


@pytest.mark.asyncio
async def test_plan_prioritizes_paused_runs(db_session: AsyncSession):
    """Plan puts paused runs first."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session, code="CC-PR")

    # Create a paused run
    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.paused,
        started_at=datetime.now(timezone.utc),
        total_steps=3,
        completed_steps=1,
    )
    db_session.add(run)
    await db_session.flush()

    result = await coach_service.plan(db_session, user_id=user.id)
    assert result["steps"][0]["action"] == "resume_run"
    assert "Resume" in result["steps"][0]["title"]


@pytest.mark.asyncio
async def test_plan_goal_focused_template(db_session: AsyncSession):
    """Plan uses goal_focused template when goals exist."""
    user = await _create_user(db_session)
    await _create_goal(db_session, user.id, title="Pay off credit card")

    result = await coach_service.plan(db_session, user_id=user.id)
    assert result["template_used"] == "goal_focused"
    assert "Pay off credit card" in result["response"]


@pytest.mark.asyncio
async def test_plan_with_encouraging_tone(db_session: AsyncSession):
    """Plan personalizes response with coach memory tone."""
    user = await _create_user(db_session)

    # Grant consent and set tone
    consent = ConsentRecord(
        user_id=user.id, consent_type=ConsentType.ai_memory, granted=True
    )
    db_session.add(consent)
    await db_session.flush()

    await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        tone=CoachTone.encouraging,
        aggressiveness=CoachAggressiveness.moderate,
    )

    result = await coach_service.plan(db_session, user_id=user.id)
    assert "You're doing well!" in result["response"]


@pytest.mark.asyncio
async def test_plan_conservative_caveat(db_session: AsyncSession):
    """Conservative aggressiveness adds 'take your time' caveat."""
    user = await _create_user(db_session)
    consent = ConsentRecord(
        user_id=user.id, consent_type=ConsentType.ai_memory, granted=True
    )
    db_session.add(consent)
    await db_session.flush()

    await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        aggressiveness=CoachAggressiveness.conservative,
    )

    result = await coach_service.plan(db_session, user_id=user.id)
    assert any("no rush" in c for c in result["caveats"])


@pytest.mark.asyncio
async def test_plan_aggressive_caveat(db_session: AsyncSession):
    """Aggressive aggressiveness adds urgency caveat."""
    user = await _create_user(db_session)
    consent = ConsentRecord(
        user_id=user.id, consent_type=ConsentType.ai_memory, granted=True
    )
    db_session.add(consent)
    await db_session.flush()

    await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        aggressiveness=CoachAggressiveness.aggressive,
    )

    result = await coach_service.plan(db_session, user_id=user.id)
    assert any("today" in c for c in result["caveats"])


@pytest.mark.asyncio
async def test_plan_audit_logged(db_session: AsyncSession):
    """Plan mode is audit-logged."""
    from app.models.audit import AuditLogEvent
    from sqlalchemy import select

    user = await _create_user(db_session)
    await coach_service.plan(db_session, user_id=user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "coach.plan",
        )
    )
    event = result.scalar_one()
    assert event.detail["template_used"] is not None
    assert "step_count" in event.detail


@pytest.mark.asyncio
async def test_plan_skips_in_progress_codes(db_session: AsyncSession):
    """Plan doesn't recommend codes user already has in progress."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session, code="CC-SKIP")

    # Create in-progress run
    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.in_progress,
        started_at=datetime.now(timezone.utc),
        total_steps=2,
        completed_steps=0,
    )
    db_session.add(run)
    await db_session.flush()

    # Create recommendation for same code
    await _create_recommendation(db_session, user.id, defn.id)

    result = await coach_service.plan(db_session, user_id=user.id)
    # The recommendation for the in-progress code should be skipped
    for step in result["steps"]:
        if step["action"] == "start_recommendation":
            assert "Test Cheat Code" not in step["title"]
