"""Phase 6 service tests: coach review mode."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeCategory,
    CheatCodeOutcome,
    CheatCodeRun,
    OutcomeType,
    Recommendation,
    RunStatus,
    VerificationStatus,
)
from app.models.consent import ConsentRecord, ConsentType
from app.models.coach_memory import CoachTone, CoachAggressiveness
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.goal import Goal, GoalType, GoalPriority
from app.models.user import User
from app.services import coach_service, coach_memory_service


async def _create_user(db: AsyncSession, email: str = "review@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _create_definition(db: AsyncSession, code: str = "CC-REV", title: str = "Review Test Code") -> CheatCodeDefinition:
    defn = CheatCodeDefinition(
        code=code,
        title=title,
        description="A test code for review",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=10,
        steps=[{"step_number": 1, "title": "Step", "description": "Do", "estimated_minutes": 5}],
        potential_savings_min=Decimal("5.00"),
        potential_savings_max=Decimal("25.00"),
    )
    db.add(defn)
    await db.flush()
    return defn


async def _create_completed_run(
    db: AsyncSession, user_id, defn_id, savings: Decimal | None = None
) -> CheatCodeRun:
    run = CheatCodeRun(
        user_id=user_id,
        cheat_code_id=defn_id,
        status=RunStatus.completed,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_steps=1,
        completed_steps=1,
    )
    db.add(run)
    await db.flush()

    if savings is not None:
        outcome = CheatCodeOutcome(
            run_id=run.id,
            user_id=user_id,
            outcome_type=OutcomeType.user_reported,
            reported_savings=savings,
            reported_savings_period="monthly",
            verification_status=VerificationStatus.unverified,
        )
        db.add(outcome)
        await db.flush()

    return run


# --- Review mode ---

@pytest.mark.asyncio
async def test_review_no_wins(db_session: AsyncSession):
    """Review with no completed runs shows no_wins template."""
    user = await _create_user(db_session)
    result = await coach_service.review(db_session, user_id=user.id)

    assert result["mode"] == "review"
    assert result["template_used"] == "no_wins"
    assert result["wins"] == []
    assert any("Complete a cheat code" in c for c in result["caveats"])


@pytest.mark.asyncio
async def test_review_with_wins(db_session: AsyncSession):
    """Review with completed runs shows wins."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session)
    await _create_completed_run(db_session, user.id, defn.id, savings=Decimal("20.00"))

    result = await coach_service.review(db_session, user_id=user.id)
    assert result["template_used"] == "with_wins"
    assert len(result["wins"]) == 1
    assert result["wins"][0]["title"] == "Review Test Code"
    assert "20" in result["wins"][0]["savings"]
    assert "1 cheat code" in result["response"]


@pytest.mark.asyncio
async def test_review_multiple_wins(db_session: AsyncSession):
    """Review aggregates multiple wins."""
    user = await _create_user(db_session)
    defn1 = await _create_definition(db_session, code="CC-R1")
    defn2 = await _create_definition(db_session, code="CC-R2")

    await _create_completed_run(db_session, user.id, defn1.id, savings=Decimal("15.00"))
    await _create_completed_run(db_session, user.id, defn2.id, savings=Decimal("25.00"))

    result = await coach_service.review(db_session, user_id=user.id)
    assert len(result["wins"]) == 2
    assert "$40" in result["response"]  # total savings


@pytest.mark.asyncio
async def test_review_includes_archived_runs(db_session: AsyncSession):
    """Review counts archived runs as wins too."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session, code="CC-AR")

    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.archived,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_steps=1,
        completed_steps=1,
    )
    db_session.add(run)
    await db_session.flush()

    result = await coach_service.review(db_session, user_id=user.id)
    assert len(result["wins"]) == 1


@pytest.mark.asyncio
async def test_review_improvement_urgency(db_session: AsyncSession):
    """Review identifies high urgency as improvement area."""
    user = await _create_user(db_session)

    # Create forecast with high urgency
    snap = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("50.00"),
        safe_to_spend_week=Decimal("100.00"),
        daily_balances=[],
        projected_end_balance=Decimal("200.00"),
        projected_end_low=Decimal("100.00"),
        projected_end_high=Decimal("300.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={"data_days": 30},
        assumptions=["test"],
        urgency_score=75,
        urgency_factors=["high spending"],
        computed_at=datetime.now(timezone.utc),
    )
    db_session.add(snap)
    await db_session.flush()

    result = await coach_service.review(db_session, user_id=user.id)
    assert "urgency" in result["inputs"]["improvement"].lower()


@pytest.mark.asyncio
async def test_review_next_move_recommendation(db_session: AsyncSession):
    """Review suggests top recommendation as next move."""
    user = await _create_user(db_session)
    defn = await _create_definition(db_session, code="CC-NM", title="Quick Budget Fix")
    rec = Recommendation(
        user_id=user.id,
        cheat_code_id=defn.id,
        rank=1,
        explanation="Top pick",
        explanation_template="general",
        explanation_inputs={},
        confidence="high",
        is_quick_win=True,
    )
    db_session.add(rec)
    await db_session.flush()

    result = await coach_service.review(db_session, user_id=user.id)
    assert "Quick Budget Fix" in result["inputs"]["next_move"]


@pytest.mark.asyncio
async def test_review_with_tone(db_session: AsyncSession):
    """Review uses tone opener from coach memory."""
    user = await _create_user(db_session)
    consent = ConsentRecord(
        user_id=user.id, consent_type=ConsentType.ai_memory, granted=True
    )
    db_session.add(consent)
    await db_session.flush()

    await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        tone=CoachTone.direct,
        aggressiveness=CoachAggressiveness.aggressive,
    )

    result = await coach_service.review(db_session, user_id=user.id)
    assert "Action needed:" in result["response"]


@pytest.mark.asyncio
async def test_review_audit_logged(db_session: AsyncSession):
    """Review mode is audit-logged."""
    from app.models.audit import AuditLogEvent
    from sqlalchemy import select

    user = await _create_user(db_session)
    await coach_service.review(db_session, user_id=user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "coach.review",
        )
    )
    event = result.scalar_one()
    assert event.detail["wins_count"] == 0
