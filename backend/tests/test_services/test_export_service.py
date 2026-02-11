"""Tests for export_service — validates every entity type serializes correctly.

The original test only created user + consent, leaving constraints, onboarding,
forecast, and other Phase 2-8 entities untested. This caused 3 runtime bugs
(UserConstraint.value, OnboardingState.completed_steps, ForecastSnapshot
Decimal/enum serialization) that went undetected through 615 tests.

This rewritten test creates EVERY entity type and verifies each field
in the export output.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import register_user
from app.models.account import Account, AccountType
from app.models.cheat_code import (
    CheatCodeCategory,
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeOutcome,
    CheatCodeRun,
    OutcomeType,
    Recommendation,
    RunStatus,
    VerificationStatus,
)
from app.models.coach_memory import CoachAggressiveness, CoachMemory, CoachTone
from app.models.consent import ConsentType
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.goal import Goal, GoalPriority, GoalType, UserConstraint
from app.models.learn import LessonCategory, LessonDefinition, LessonProgress, LessonStatus
from app.models.onboarding import OnboardingState, OnboardingStep
from app.models.practice import ScenarioCategory, ScenarioDefinition, ScenarioRun, ScenarioRunStatus
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.transaction import Transaction, TransactionType
from app.models.vault import VaultItem, VaultItemType
from app.services import audit_service, consent_service, export_service


_NOW = datetime.now(timezone.utc)


async def _create_full_user(db: AsyncSession) -> uuid.UUID:
    """Create a user with at least one instance of EVERY entity type.

    Returns the user_id.
    """
    # ── User ──
    user = await register_user(db, email="export-full@example.com", password="Pass123!", ip_address="10.0.0.1")
    await db.commit()
    uid = user.id

    # ── Consent ──
    await consent_service.grant_consent(db, user_id=uid, consent_type=ConsentType.data_access, ip_address="10.0.0.1")
    await consent_service.grant_consent(db, user_id=uid, consent_type=ConsentType.terms_of_service, ip_address="10.0.0.1")
    await db.commit()

    # ── Account ──
    account = Account(
        user_id=uid,
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Main Checking",
        current_balance=Decimal("1500.00"),
        currency="USD",
    )
    db.add(account)
    await db.flush()

    # ── Transaction ──
    txn = Transaction(
        user_id=uid,
        account_id=account.id,
        raw_description="GROCERY MART",
        normalized_description="Grocery Mart",
        amount=Decimal("45.67"),
        transaction_type=TransactionType.debit,
        transaction_date=_NOW,
        currency="USD",
    )
    db.add(txn)
    await db.flush()

    # ── RecurringPattern ──
    pattern = RecurringPattern(
        user_id=uid,
        estimated_amount=Decimal("15.99"),
        amount_variance=Decimal("0.00"),
        frequency=Frequency.monthly,
        confidence=Confidence.high,
        is_active=True,
        is_manual=False,
        is_essential=False,
        label="Netflix",
    )
    db.add(pattern)
    await db.flush()

    # ── Goal ──
    goal = Goal(
        user_id=uid,
        goal_type=GoalType.save_money,
        title="Emergency fund",
        priority=GoalPriority.high,
    )
    db.add(goal)
    await db.flush()

    # ── UserConstraint ──
    constraint = UserConstraint(
        user_id=uid,
        constraint_type="fixed",
        label="Rent is non-negotiable",
        amount=Decimal("1200.00"),
        notes="Monthly rent",
    )
    db.add(constraint)
    await db.flush()

    # ── OnboardingState ──
    onboarding = OnboardingState(
        user_id=uid,
        current_step=OnboardingStep.goals,
        consent_completed_at=_NOW,
        account_completed_at=_NOW,
    )
    db.add(onboarding)
    await db.flush()

    # ── CheatCodeDefinition ──
    cc_def = CheatCodeDefinition(
        code="CC-TEST-001",
        title="Test Cheat Code",
        description="A test cheat code for export validation",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=5,
        steps=[{"step_number": 1, "title": "Step 1", "description": "Do the thing", "estimated_minutes": 5}],
    )
    db.add(cc_def)
    await db.flush()

    # ── Recommendation ──
    rec = Recommendation(
        user_id=uid,
        cheat_code_id=cc_def.id,
        rank=1,
        explanation="You should do this because reasons",
        explanation_template="recommendation_general",
        explanation_inputs={"reason": "test"},
        confidence="high",
        is_quick_win=True,
    )
    db.add(rec)
    await db.flush()

    # ── CheatCodeRun ──
    run = CheatCodeRun(
        user_id=uid,
        cheat_code_id=cc_def.id,
        recommendation_id=rec.id,
        status=RunStatus.in_progress,
        started_at=_NOW,
        total_steps=1,
        completed_steps=0,
    )
    db.add(run)
    await db.flush()

    # ── CheatCodeOutcome ──
    outcome = CheatCodeOutcome(
        user_id=uid,
        run_id=run.id,
        outcome_type=OutcomeType.user_reported,
        reported_savings=Decimal("50.00"),
        verification_status=VerificationStatus.unverified,
    )
    db.add(outcome)
    await db.flush()

    # ── ForecastSnapshot ──
    forecast = ForecastSnapshot(
        user_id=uid,
        safe_to_spend_today=Decimal("800.00"),
        safe_to_spend_week=Decimal("600.00"),
        daily_balances=[{"day": 1, "projected": 1500.00, "low": 1400.00, "high": 1600.00}],
        projected_end_balance=Decimal("1200.00"),
        projected_end_low=Decimal("1000.00"),
        projected_end_high=Decimal("1400.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={"data_days": 45, "high_conf_patterns": 1},
        assumptions=["Income of $3000 expected on 2026-02-15", "1 recurring charge totaling $15.99"],
        urgency_score=35,
        urgency_factors={"low_balance": False, "negative_sts": False},
    )
    db.add(forecast)
    await db.flush()

    # ── CoachMemory ──
    coach_mem = CoachMemory(
        user_id=uid,
        tone=CoachTone.encouraging,
        aggressiveness=CoachAggressiveness.moderate,
    )
    db.add(coach_mem)
    await db.flush()

    # ── LessonDefinition + LessonProgress ──
    lesson = LessonDefinition(
        code="L-TEST-001",
        title="Test Lesson",
        description="A test lesson",
        category=LessonCategory.save_money,
        sections=[{"section_number": 1, "title": "Intro", "content": "Hello", "key_takeaway": "Save"}],
        total_sections=1,
        estimated_minutes=5,
        display_order=1,
    )
    db.add(lesson)
    await db.flush()

    lesson_prog = LessonProgress(
        user_id=uid,
        lesson_id=lesson.id,
        status=LessonStatus.in_progress,
        completed_sections=0,
    )
    db.add(lesson_prog)
    await db.flush()

    # ── ScenarioDefinition + ScenarioRun ──
    scenario = ScenarioDefinition(
        code="S-TEST-001",
        title="Test Scenario",
        description="A test scenario",
        category=ScenarioCategory.save_money,
        initial_state={"balance": 5000},
        sliders=[{"key": "savings", "label": "Monthly Savings", "min": 0, "max": 1000, "step": 50, "default": 200}],
        outcome_template="You will save {projected_savings}",
        learning_points=["Saving works"],
        estimated_minutes=10,
        display_order=1,
    )
    db.add(scenario)
    await db.flush()

    scenario_run = ScenarioRun(
        user_id=uid,
        scenario_id=scenario.id,
        slider_values={"savings": 500},
        status=ScenarioRunStatus.completed,
        confidence="medium",
        plan_generated=False,
    )
    db.add(scenario_run)
    await db.flush()

    # ── VaultItem ──
    vault_item = VaultItem(
        user_id=uid,
        transaction_id=txn.id,
        filename="receipt.pdf",
        content_type="application/pdf",
        file_size=12345,
        item_type=VaultItemType.receipt,
        storage_key=f"{uid}_test_receipt.pdf",
        description="Test receipt",
    )
    db.add(vault_item)
    await db.commit()

    return uid


@pytest.mark.asyncio
async def test_export_every_entity_type(db_session: AsyncSession):
    """Create one of EVERY entity type -> export -> verify all fields serialize.

    This test would have caught the 3 bugs:
    - UserConstraint.value (nonexistent)
    - OnboardingState.completed_steps (nonexistent)
    - ForecastSnapshot Decimal/enum not serialized
    """
    uid = await _create_full_user(db_session)
    data = await export_service.export_user_data(db_session, uid, ip_address="10.0.0.1")
    await db_session.commit()

    # ── Top-level keys present ──
    required_keys = [
        "user", "consent_records", "accounts", "transactions",
        "recurring_patterns", "goals", "constraints", "onboarding",
        "recommendations", "cheat_code_runs", "cheat_code_outcomes",
        "forecasts", "coach_memory", "lesson_progress", "scenario_runs",
        "vault_items", "audit_log",
    ]
    for key in required_keys:
        assert key in data, f"Missing top-level key: {key}"

    # ── User ──
    assert data["user"]["email"] == "export-full@example.com"
    assert data["user"]["status"] == "active"
    assert isinstance(data["user"]["id"], str)
    assert isinstance(data["user"]["created_at"], str)

    # ── Consent records (data_access + terms_of_service) ──
    assert len(data["consent_records"]) == 2
    c = data["consent_records"][0]
    assert isinstance(c["id"], str)
    assert c["consent_type"] in ("data_access", "terms_of_service")
    assert c["granted"] is True
    assert isinstance(c["granted_at"], str)

    # ── Accounts ──
    assert len(data["accounts"]) == 1
    a = data["accounts"][0]
    assert a["institution_name"] == "Test Bank"
    assert a["account_name"] == "Main Checking"
    assert a["account_type"] in ("checking",)  # AccountType enum stored as string by SA

    # ── Transactions ──
    assert len(data["transactions"]) == 1
    t = data["transactions"][0]
    assert isinstance(t["id"], str)
    assert isinstance(t["amount"], str)  # Decimal -> str via _serialize_decimal
    assert t["transaction_type"] == "debit"
    assert t["normalized_description"] == "Grocery Mart"

    # ── Recurring patterns ──
    assert len(data["recurring_patterns"]) == 1
    rp = data["recurring_patterns"][0]
    assert rp["frequency"] == "monthly"
    assert rp["confidence"] == "high"
    assert isinstance(rp["estimated_amount"], str)
    assert rp["is_manual"] is False
    assert rp["is_essential"] is False
    assert rp["label"] == "Netflix"

    # ── Goals ──
    assert len(data["goals"]) == 1
    g = data["goals"][0]
    assert g["title"] == "Emergency fund"
    assert g["goal_type"] == "save_money"

    # ── Constraints — THIS was the first bug (uc.value) ──
    assert len(data["constraints"]) == 1
    uc = data["constraints"][0]
    assert isinstance(uc["id"], str)
    assert uc["constraint_type"] == "fixed"
    assert uc["label"] == "Rent is non-negotiable"
    assert uc["amount"] == "1200.00"
    assert uc["notes"] == "Monthly rent"

    # ── Onboarding — THIS was the second bug (completed_steps) ──
    ob = data["onboarding"]
    assert ob is not None
    assert ob["current_step"] == "goals"
    assert isinstance(ob["consent_completed_at"], str)
    assert isinstance(ob["account_completed_at"], str)
    assert ob["goals_completed_at"] is None  # not completed yet
    assert ob["top_3_completed_at"] is None
    assert ob["first_win_completed_at"] is None

    # ── Recommendations ──
    assert len(data["recommendations"]) == 1
    rec = data["recommendations"][0]
    assert isinstance(rec["id"], str)
    assert rec["rank"] == 1
    assert rec["confidence"] == "high"
    assert rec["explanation"] == "You should do this because reasons"

    # ── Cheat code runs ──
    assert len(data["cheat_code_runs"]) == 1
    run = data["cheat_code_runs"][0]
    assert run["status"] == "in_progress"
    assert isinstance(run["started_at"], str)

    # ── Cheat code outcomes ──
    assert len(data["cheat_code_outcomes"]) == 1
    out = data["cheat_code_outcomes"][0]
    assert isinstance(out["reported_savings"], str)

    # ── Forecasts — THIS was the third bug (Decimal/enum serialization) ──
    assert len(data["forecasts"]) == 1
    f = data["forecasts"][0]
    assert isinstance(f["id"], str)
    assert isinstance(f["safe_to_spend_today"], str)  # Decimal -> str
    assert isinstance(f["safe_to_spend_week"], str)   # Decimal -> str
    assert f["confidence"] == "medium"                 # enum -> str
    assert f["urgency_score"] == 35
    assert isinstance(f["computed_at"], str)

    # ── Coach memory ──
    cm = data["coach_memory"]
    assert cm is not None
    assert cm["tone"] == "encouraging"
    assert cm["aggressiveness"] == "moderate"

    # ── Lesson progress ──
    assert len(data["lesson_progress"]) == 1
    lp = data["lesson_progress"][0]
    assert lp["status"] == "in_progress"
    assert lp["completed_sections"] == 0

    # ── Scenario runs ──
    assert len(data["scenario_runs"]) == 1
    sr = data["scenario_runs"][0]
    assert sr["status"] == "completed"
    assert sr["confidence"] == "medium"
    assert sr["plan_generated"] is False

    # ── Vault items ──
    assert len(data["vault_items"]) == 1
    vi = data["vault_items"][0]
    assert vi["filename"] == "receipt.pdf"
    assert vi["content_type"] == "application/pdf"
    assert vi["file_size"] == 12345
    assert vi["item_type"] == "receipt"
    assert vi["description"] == "Test receipt"
    assert isinstance(vi["transaction_id"], str)

    # ── Audit log ──
    assert len(data["audit_log"]) >= 2  # register + consent grants
    event_types = [e["event_type"] for e in data["audit_log"]]
    assert "auth.register" in event_types
    assert "consent.granted" in event_types


@pytest.mark.asyncio
async def test_export_logs_to_audit(db_session: AsyncSession):
    """Export event itself is logged to audit."""
    user = await register_user(
        db_session, email="export-audit@example.com", password="Pass123!"
    )
    await db_session.commit()

    await export_service.export_user_data(db_session, user.id, ip_address="10.0.0.2")
    await db_session.commit()

    events = await audit_service.get_events_for_user(db_session, user.id)
    export_events = [e for e in events if e.event_type == "user.data_exported"]
    assert len(export_events) == 1
    assert export_events[0].ip_address == "10.0.0.2"


@pytest.mark.asyncio
async def test_export_empty_user(db_session: AsyncSession):
    """Export a user with no entities beyond registration — should not error."""
    user = await register_user(
        db_session, email="empty-export@example.com", password="Pass123!"
    )
    await db_session.commit()

    data = await export_service.export_user_data(db_session, user.id)
    await db_session.commit()

    assert data["user"]["email"] == "empty-export@example.com"
    assert len(data["accounts"]) == 0
    assert len(data["transactions"]) == 0
    assert len(data["constraints"]) == 0
    assert data["onboarding"] is None
    assert len(data["forecasts"]) == 0
    assert data["coach_memory"] is None
    assert len(data["vault_items"]) == 0


@pytest.mark.asyncio
async def test_export_nonexistent_user(db_session: AsyncSession):
    """Export for nonexistent user returns error dict."""
    data = await export_service.export_user_data(db_session, uuid.uuid4())
    assert data == {"error": "User not found"}
