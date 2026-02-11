"""Phase 6 integration test: full coach plan/review/recap flow with financial data."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category
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
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.goal import Goal, GoalType, GoalPriority
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.transaction import Transaction, TransactionType


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p6integ@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p6integ@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


@pytest.mark.asyncio
async def test_full_coach_phase6_flow(client: AsyncClient, db_session: AsyncSession):
    """End-to-end: set memory → plan → execute code → review → recap."""
    import uuid as uuid_mod

    headers, user_id_str = await _register_and_login(client)
    uid = uuid_mod.UUID(user_id_str)
    now = datetime.now(timezone.utc)

    # --- Setup financial data ---

    # Grant ai_memory consent
    consent = ConsentRecord(
        user_id=uid, consent_type=ConsentType.ai_memory, granted=True
    )
    db_session.add(consent)
    await db_session.flush()

    # Set coach memory: encouraging + moderate
    resp = await client.put(
        "/coach/memory",
        json={"tone": "encouraging", "aggressiveness": "moderate"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["tone"] == "encouraging"

    # Create goal
    goal = Goal(
        user_id=uid,
        goal_type=GoalType.save_money,
        title="Save $500 this month",
        priority=GoalPriority.high,
    )
    db_session.add(goal)
    await db_session.flush()

    # Create account + transactions
    acct = Account(
        user_id=uid,
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Main Checking",
        available_balance=Decimal("2000.00"),
        current_balance=Decimal("2000.00"),
        currency="USD",
    )
    db_session.add(acct)
    await db_session.flush()

    cat = Category(name="Dining", is_system=True)
    db_session.add(cat)
    await db_session.flush()

    for i in range(5):
        txn = Transaction(
            user_id=uid,
            account_id=acct.id,
            raw_description=f"Restaurant {i}",
            normalized_description=f"restaurant {i}",
            amount=Decimal("30.00"),
            transaction_type=TransactionType.debit,
            transaction_date=now - timedelta(days=i),
            category_id=cat.id,
        )
        db_session.add(txn)
    await db_session.flush()

    # Create cheat code + recommendation
    defn = CheatCodeDefinition(
        code="CC-INT6",
        title="Cancel Unused Streaming",
        description="Review and cancel streaming services you don't use.",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=10,
        steps=[
            {"step_number": 1, "title": "List services", "description": "Write down all streaming", "estimated_minutes": 3},
            {"step_number": 2, "title": "Cancel unused", "description": "Cancel the ones you don't use", "estimated_minutes": 7},
        ],
        potential_savings_min=Decimal("10.00"),
        potential_savings_max=Decimal("30.00"),
    )
    db_session.add(defn)
    await db_session.flush()

    rec = Recommendation(
        user_id=uid,
        cheat_code_id=defn.id,
        rank=1,
        explanation="You have recurring subscriptions that could be cancelled.",
        explanation_template="subscription_cancel",
        explanation_inputs={"recurring_count": 3, "savings_min": "10", "savings_max": "30"},
        confidence="high",
        is_quick_win=True,
    )
    db_session.add(rec)
    await db_session.flush()

    # Create forecast
    snap = ForecastSnapshot(
        user_id=uid,
        safe_to_spend_today=Decimal("150.00"),
        safe_to_spend_week=Decimal("400.00"),
        daily_balances=[],
        projected_end_balance=Decimal("1500.00"),
        projected_end_low=Decimal("1000.00"),
        projected_end_high=Decimal("2000.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={"data_days": 45},
        assumptions=["Based on 45 days of data"],
        urgency_score=30,
        urgency_factors=["moderate spending"],
        computed_at=now,
    )
    db_session.add(snap)
    await db_session.flush()

    # --- Step 1: Plan ---
    resp = await client.post(
        "/coach",
        json={"mode": "plan"},
        headers=headers,
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["mode"] == "plan"
    assert plan["template_used"] == "goal_focused"
    assert "Save $500" in plan["response"]
    assert "You're doing well!" in plan["response"]  # encouraging tone
    assert len(plan["steps"]) >= 1
    assert len(plan["steps"]) <= 3

    # Verify plan includes recommendation
    rec_steps = [s for s in plan["steps"] if s["action"] == "start_recommendation"]
    assert len(rec_steps) >= 1
    assert "Cancel Unused Streaming" in rec_steps[0]["title"]

    # --- Step 2: Simulate completing the cheat code ---
    run = CheatCodeRun(
        user_id=uid,
        cheat_code_id=defn.id,
        recommendation_id=rec.id,
        status=RunStatus.completed,
        started_at=now - timedelta(hours=1),
        completed_at=now,
        total_steps=2,
        completed_steps=2,
    )
    db_session.add(run)
    await db_session.flush()

    outcome = CheatCodeOutcome(
        run_id=run.id,
        user_id=uid,
        outcome_type=OutcomeType.user_reported,
        reported_savings=Decimal("15.00"),
        reported_savings_period="monthly",
        verification_status=VerificationStatus.unverified,
    )
    db_session.add(outcome)
    await db_session.flush()

    # --- Step 3: Review ---
    resp = await client.post(
        "/coach",
        json={"mode": "review"},
        headers=headers,
    )
    assert resp.status_code == 200
    review = resp.json()
    assert review["mode"] == "review"
    assert review["template_used"] == "with_wins"
    assert len(review["wins"]) == 1
    assert review["wins"][0]["title"] == "Cancel Unused Streaming"
    assert "15" in review["wins"][0]["savings"]
    assert "You're doing well!" in review["response"]  # encouraging tone

    # --- Step 4: Recap ---
    resp = await client.post(
        "/coach",
        json={"mode": "recap"},
        headers=headers,
    )
    assert resp.status_code == 200
    recap = resp.json()
    assert recap["mode"] == "recap"
    assert recap["template_used"] == "active_week"
    assert recap["inputs"]["txn_count"] == 5
    assert "Dining" in recap["inputs"]["top_category_note"]
    assert "1 completed this week" in recap["inputs"]["run_progress"]
    assert "150" in recap["inputs"]["forecast_note"]
    assert "Save $500" in recap["inputs"]["goal_note"]

    # --- Step 5: Verify memory is readable ---
    resp = await client.get("/coach/memory", headers=headers)
    assert resp.status_code == 200
    mem = resp.json()
    assert mem["tone"] == "encouraging"
    assert mem["aggressiveness"] == "moderate"

    # --- Step 6: Delete memory ---
    resp = await client.delete("/coach/memory", headers=headers)
    assert resp.status_code == 204

    # After delete, plan still works (falls back to defaults)
    resp = await client.post(
        "/coach",
        json={"mode": "plan"},
        headers=headers,
    )
    assert resp.status_code == 200
    # Should not have encouraging tone opener anymore
    plan2 = resp.json()
    assert "You're doing well!" not in plan2["response"]
