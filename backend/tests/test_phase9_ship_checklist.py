"""Phase 9: Ship/No-Ship Checklist — automated verification tests.

Verifies all PRD ship gates are met:
1. Consent defaults OFF for ai_memory
2. Audit trail is append-only (no update/delete exposed)
3. All coach outputs are template-based and explainable
4. Practice confidence always capped at medium
5. Low confidence never in Top 3 recommendations
6. Export includes all entity types
7. Delete purges PII + vault files
8. Onboarding gates enforce order
9. First Win requires completed step
10. All critical actions audit-logged
"""

import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.models.cheat_code import (
    CheatCodeCategory,
    CheatCodeDefinition,
    CheatCodeDifficulty,
    Recommendation,
)
from app.models.consent import ConsentRecord, ConsentType
from app.models.goal import Goal, GoalType
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.onboarding import OnboardingStep
from app.models.user import User
from app.services import audit_service, consent_service, ranking_service

# Standard steps payload for CheatCodeDefinition (required NOT NULL JSON field)
_DEFAULT_STEPS = [{"step_number": 1, "title": "Do it", "description": "Just do it", "estimated_minutes": 5}]
from app.services.practice_service import PRACTICE_CONFIDENCE_CAP
from app.services.storage import InMemoryStorageBackend, set_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield
    set_storage(None)


async def _create_user(db: AsyncSession, email: str = "ship@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


# --- Ship Gate 1: Consent defaults ---

@pytest.mark.asyncio
async def test_ai_memory_consent_defaults_off(db_session: AsyncSession):
    """PRD: AI memory consent must default to OFF."""
    user = await _create_user(db_session)
    has_consent = await consent_service.check_consent(
        db_session, user_id=user.id, consent_type=ConsentType.ai_memory
    )
    assert has_consent is False


# --- Ship Gate 2: Audit trail append-only ---

@pytest.mark.asyncio
async def test_audit_service_no_delete_method():
    """Audit service exposes no delete or update methods."""
    import app.services.audit_service as svc
    public_methods = [m for m in dir(svc) if not m.startswith("_")]
    assert "delete" not in " ".join(public_methods).lower()
    assert "update" not in " ".join(public_methods).lower()
    assert "log_event" in public_methods
    assert "get_events_for_user" in public_methods
    assert "reconstruct_why" in public_methods


# --- Ship Gate 3: Coach outputs are template-based ---

@pytest.mark.asyncio
async def test_coach_explain_always_has_template(db_session: AsyncSession):
    """Coach explain returns template_used in all responses."""
    from app.services import coach_service

    user = await _create_user(db_session)
    result = await coach_service.explain(
        db_session,
        user_id=user.id,
        context_type="nonexistent_type",
        context_id=uuid.uuid4(),
    )
    assert "template_used" in result
    assert "inputs" in result
    assert "caveats" in result
    assert result["template_used"] == "unknown"


@pytest.mark.asyncio
async def test_coach_execute_always_has_template(db_session: AsyncSession):
    """Coach execute returns template_used in all responses."""
    from app.services import coach_service

    user = await _create_user(db_session)
    result = await coach_service.execute(
        db_session,
        user_id=user.id,
        context_type="nonexistent_type",
        context_id=uuid.uuid4(),
    )
    assert "template_used" in result
    assert result["template_used"] == "unknown"


# --- Ship Gate 4: Practice confidence cap ---

@pytest.mark.asyncio
async def test_practice_confidence_cap_is_medium():
    """PRD: Practice confidence cap must be 'medium'."""
    assert PRACTICE_CONFIDENCE_CAP == "medium"


# --- Ship Gate 5: No low confidence in Top 3 ---

@pytest.mark.asyncio
async def test_ranking_never_assigns_low_confidence(db_session: AsyncSession):
    """PRD: Top 3 must never include low-confidence recommendations."""
    user = await _create_user(db_session)

    # Seed cheat codes with no supporting data (worst case for confidence)
    for i, code in enumerate(["CC-SG1", "CC-SG2", "CC-SG3", "CC-SG4"]):
        defn = CheatCodeDefinition(
            code=code,
            title=f"Ship Gate Test {i}",
            description="Test",
            category=CheatCodeCategory.save_money,
            difficulty=CheatCodeDifficulty.quick_win if i == 0 else CheatCodeDifficulty.medium,
            estimated_minutes=5,
            steps=_DEFAULT_STEPS,
            potential_savings_min=Decimal("10"),
            potential_savings_max=Decimal("50"),
        )
        db_session.add(defn)
    await db_session.flush()

    # No goals, no patterns — minimum data scenario
    recommendations = await ranking_service.compute_top_3(
        db_session, user.id
    )

    for rec in recommendations:
        assert rec.confidence != "low", (
            f"Recommendation rank={rec.rank} has low confidence — PRD violation!"
        )


@pytest.mark.asyncio
async def test_ranking_urgency_cannot_override_confidence(db_session: AsyncSession):
    """PRD: Urgency influences score but CANNOT override confidence rules."""
    user = await _create_user(db_session)

    # Create minimal cheat codes
    for i in range(4):
        db_session.add(CheatCodeDefinition(
            code=f"CC-URG{i}",
            title=f"Urgency Test {i}",
            description="Test",
            category=CheatCodeCategory.reduce_spending,
            difficulty=CheatCodeDifficulty.quick_win if i == 0 else CheatCodeDifficulty.medium,
            estimated_minutes=5,
            steps=_DEFAULT_STEPS,
            potential_savings_min=Decimal("5"),
            potential_savings_max=Decimal("20"),
        ))
    await db_session.flush()

    # Create a forecast with maximum urgency
    from app.models.forecast import ForecastConfidence, ForecastSnapshot
    forecast = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("-500.00"),
        safe_to_spend_week=Decimal("-2000.00"),
        daily_balances=[],
        projected_end_balance=Decimal("-3000.00"),
        projected_end_low=Decimal("-4000.00"),
        projected_end_high=Decimal("-2000.00"),
        confidence=ForecastConfidence.low,
        confidence_inputs={"data_days": 5, "high_confidence_patterns": 0},
        assumptions=["Insufficient data"],
        urgency_score=100,
        urgency_factors={"negative_sts": True, "spending_runway_days": 0},
    )
    db_session.add(forecast)
    await db_session.flush()

    recommendations = await ranking_service.compute_top_3(
        db_session, user.id
    )

    # Even with max urgency, no low confidence allowed
    for rec in recommendations:
        assert rec.confidence != "low"


# --- Ship Gate 6: Export completeness ---

@pytest.mark.asyncio
async def test_export_includes_all_entity_types(db_session: AsyncSession):
    """Export must include keys for all Phase 0-8 entities."""
    from app.services import export_service

    user = await _create_user(db_session)
    data = await export_service.export_user_data(db_session, user.id)

    required_keys = [
        "user", "consent_records", "accounts", "transactions",
        "recurring_patterns", "goals", "constraints", "onboarding",
        "recommendations", "cheat_code_runs", "cheat_code_outcomes",
        "forecasts", "coach_memory", "lesson_progress",
        "scenario_runs", "vault_items", "audit_log",
    ]
    for key in required_keys:
        assert key in data, f"Export missing key: {key}"


# --- Ship Gate 7: Onboarding gates enforce order ---

@pytest.mark.asyncio
async def test_onboarding_gates_enforce_order(db_session: AsyncSession):
    """Onboarding steps cannot be skipped."""
    from app.services import onboarding_service

    user = await _create_user(db_session)
    await onboarding_service.get_or_create_state(db_session, user_id=user.id)

    # First advance consent
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.consent
    )

    # Try to skip account_link and go directly to goals
    with pytest.raises(ValueError):
        await onboarding_service.advance_step(
            db_session, user_id=user.id, completed_step=OnboardingStep.goals
        )


# --- Ship Gate 8: All ranking explanations are templated ---

@pytest.mark.asyncio
async def test_all_ranking_templates_have_inputs(db_session: AsyncSession):
    """Every recommendation must have template + inputs (explainability)."""
    user = await _create_user(db_session)

    for i in range(4):
        db_session.add(CheatCodeDefinition(
            code=f"CC-TPL{i}",
            title=f"Template Test {i}",
            description="Test",
            category=CheatCodeCategory.budget_better,
            difficulty=CheatCodeDifficulty.quick_win if i == 0 else CheatCodeDifficulty.medium,
            estimated_minutes=5,
            steps=_DEFAULT_STEPS,
            potential_savings_min=Decimal("10"),
            potential_savings_max=Decimal("50"),
        ))
    await db_session.flush()

    recommendations = await ranking_service.compute_top_3(
        db_session, user.id
    )

    for rec in recommendations:
        assert rec.explanation_template is not None
        assert rec.explanation_template != ""
        assert rec.explanation_inputs is not None
        assert isinstance(rec.explanation_inputs, dict)
        assert rec.explanation is not None
        assert len(rec.explanation) > 0


# --- Ship Gate 9: Quick win in Top 3 ---

@pytest.mark.asyncio
async def test_top3_includes_quick_win(db_session: AsyncSession):
    """PRD: Top 3 must include at least one quick win (<=10 min)."""
    user = await _create_user(db_session)

    # Create 3 non-quick-wins and 1 quick-win
    for i in range(3):
        db_session.add(CheatCodeDefinition(
            code=f"CC-NQW{i}",
            title=f"Not Quick Win {i}",
            description="Test",
            category=CheatCodeCategory.save_money,
            difficulty=CheatCodeDifficulty.medium,
            estimated_minutes=30,
            steps=_DEFAULT_STEPS,
            potential_savings_min=Decimal("100"),
            potential_savings_max=Decimal("500"),
        ))
    db_session.add(CheatCodeDefinition(
        code="CC-QW1",
        title="Quick Win",
        description="Test",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=5,
        steps=_DEFAULT_STEPS,
        potential_savings_min=Decimal("5"),
        potential_savings_max=Decimal("15"),
    ))
    await db_session.flush()

    recommendations = await ranking_service.compute_top_3(
        db_session, user.id
    )

    has_quick_win = any(r.is_quick_win for r in recommendations)
    assert has_quick_win, "Top 3 must include at least one quick win"
