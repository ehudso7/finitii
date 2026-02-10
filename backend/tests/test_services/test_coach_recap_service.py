"""Phase 6 service tests: coach weekly recap."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category
from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeCategory,
    CheatCodeRun,
    RunStatus,
)
from app.models.consent import ConsentRecord, ConsentType
from app.models.coach_memory import CoachTone, CoachAggressiveness
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.goal import Goal, GoalType, GoalPriority
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services import coach_service, coach_memory_service


async def _create_user(db: AsyncSession, email: str = "recap@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _create_account(db: AsyncSession, user_id) -> Account:
    acct = Account(
        user_id=user_id,
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Checking",
        available_balance=Decimal("1000.00"),
        current_balance=Decimal("1000.00"),
        currency="USD",
    )
    db.add(acct)
    await db.flush()
    return acct


async def _create_transactions(
    db: AsyncSession, user_id, account_id, count: int = 5, category_id=None
):
    now = datetime.now(timezone.utc)
    for i in range(count):
        txn = Transaction(
            user_id=user_id,
            account_id=account_id,
            raw_description=f"Purchase {i}",
            normalized_description=f"purchase {i}",
            amount=Decimal("25.00"),
            transaction_type=TransactionType.debit,
            transaction_date=now - timedelta(days=i),
            category_id=category_id,
        )
        db.add(txn)
    await db.flush()


# --- Recap mode ---

@pytest.mark.asyncio
async def test_recap_no_data(db_session: AsyncSession):
    """Recap with no data returns quiet week with caveat."""
    user = await _create_user(db_session)
    result = await coach_service.recap(db_session, user_id=user.id)

    assert result["mode"] == "recap"
    assert result["template_used"] == "quiet_week"
    assert "0" in result["inputs"]["total_spent"]
    assert result["inputs"]["txn_count"] == 0
    assert any("No transactions" in c for c in result["caveats"])


@pytest.mark.asyncio
async def test_recap_with_spending(db_session: AsyncSession):
    """Recap includes spending summary from this week's transactions."""
    user = await _create_user(db_session)
    acct = await _create_account(db_session, user.id)
    await _create_transactions(db_session, user.id, acct.id, count=3)

    result = await coach_service.recap(db_session, user_id=user.id)
    assert result["inputs"]["txn_count"] == 3
    # 3 * $25 = $75
    assert "75" in result["inputs"]["total_spent"]


@pytest.mark.asyncio
async def test_recap_top_category(db_session: AsyncSession):
    """Recap identifies top spending category."""
    user = await _create_user(db_session)
    acct = await _create_account(db_session, user.id)

    cat = Category(name="Dining", is_system=True)
    db_session.add(cat)
    await db_session.flush()

    await _create_transactions(db_session, user.id, acct.id, count=4, category_id=cat.id)

    result = await coach_service.recap(db_session, user_id=user.id)
    assert "Dining" in result["inputs"]["top_category_note"]


@pytest.mark.asyncio
async def test_recap_active_week_with_runs(db_session: AsyncSession):
    """Recap uses active_week template when there's cheat code activity."""
    user = await _create_user(db_session)

    defn = CheatCodeDefinition(
        code="CC-REC",
        title="Recap Test",
        description="Test",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=5,
        steps=[{"step_number": 1, "title": "S1", "description": "D1", "estimated_minutes": 5}],
    )
    db_session.add(defn)
    await db_session.flush()

    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.completed,
        started_at=datetime.now(timezone.utc) - timedelta(days=2),
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
        total_steps=1,
        completed_steps=1,
    )
    db_session.add(run)
    await db_session.flush()

    result = await coach_service.recap(db_session, user_id=user.id)
    assert result["template_used"] == "active_week"
    assert "1 completed this week" in result["inputs"]["run_progress"]


@pytest.mark.asyncio
async def test_recap_in_progress_runs(db_session: AsyncSession):
    """Recap reports in-progress runs."""
    user = await _create_user(db_session)

    defn = CheatCodeDefinition(
        code="CC-RIP",
        title="In Progress",
        description="Test",
        category=CheatCodeCategory.budget_better,
        difficulty=CheatCodeDifficulty.easy,
        estimated_minutes=20,
        steps=[{"step_number": 1, "title": "S1", "description": "D1", "estimated_minutes": 10}],
    )
    db_session.add(defn)
    await db_session.flush()

    run = CheatCodeRun(
        user_id=user.id,
        cheat_code_id=defn.id,
        status=RunStatus.in_progress,
        started_at=datetime.now(timezone.utc) - timedelta(days=3),
        total_steps=2,
        completed_steps=1,
    )
    db_session.add(run)
    await db_session.flush()

    result = await coach_service.recap(db_session, user_id=user.id)
    assert "1 in progress" in result["inputs"]["run_progress"]


@pytest.mark.asyncio
async def test_recap_with_forecast(db_session: AsyncSession):
    """Recap includes forecast summary when available."""
    user = await _create_user(db_session)

    snap = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("150.00"),
        safe_to_spend_week=Decimal("300.00"),
        daily_balances=[],
        projected_end_balance=Decimal("500.00"),
        projected_end_low=Decimal("200.00"),
        projected_end_high=Decimal("800.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={},
        assumptions=[],
        urgency_score=20,
        urgency_factors=[],
        computed_at=datetime.now(timezone.utc),
    )
    db_session.add(snap)
    await db_session.flush()

    result = await coach_service.recap(db_session, user_id=user.id)
    assert "150" in result["inputs"]["forecast_note"]
    assert "medium" in result["inputs"]["forecast_note"]


@pytest.mark.asyncio
async def test_recap_with_goals(db_session: AsyncSession):
    """Recap lists active goals."""
    user = await _create_user(db_session)
    goal = Goal(
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Emergency Fund",
        priority=GoalPriority.high,
    )
    db_session.add(goal)
    await db_session.flush()

    result = await coach_service.recap(db_session, user_id=user.id)
    assert "Emergency Fund" in result["inputs"]["goal_note"]


@pytest.mark.asyncio
async def test_recap_no_goals(db_session: AsyncSession):
    """Recap shows 'no goals' when none set."""
    user = await _create_user(db_session)
    result = await coach_service.recap(db_session, user_id=user.id)
    assert "No active goals" in result["inputs"]["goal_note"]


@pytest.mark.asyncio
async def test_recap_tone_personalization(db_session: AsyncSession):
    """Recap uses coach memory tone."""
    user = await _create_user(db_session)
    consent = ConsentRecord(
        user_id=user.id, consent_type=ConsentType.ai_memory, granted=True
    )
    db_session.add(consent)
    await db_session.flush()

    await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        tone=CoachTone.encouraging,
        aggressiveness=CoachAggressiveness.aggressive,
    )

    result = await coach_service.recap(db_session, user_id=user.id)
    assert "momentum" in result["response"].lower()


@pytest.mark.asyncio
async def test_recap_audit_logged(db_session: AsyncSession):
    """Recap is audit-logged."""
    from app.models.audit import AuditLogEvent
    from sqlalchemy import select

    user = await _create_user(db_session)
    await coach_service.recap(db_session, user_id=user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "coach.recap",
        )
    )
    event = result.scalar_one()
    assert "period" in event.detail
    assert "total_spent" in event.detail
