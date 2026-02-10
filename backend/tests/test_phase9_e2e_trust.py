"""Phase 9: End-to-end trust verification tests.

Proves PRD trust requirements with real multi-entity data:
1. Export completeness — all entities populated and present in export
2. Delete purges PII + vault files — nothing leaks after account deletion
3. Audit trail reconstructs "why" — every critical action has a trail
4. Low confidence never in Top 3 — even with adversarial data
5. First Win hard gate — cannot bypass onboarding sequence
"""

import io
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.models.account import Account
from app.models.audit import AuditLogEvent
from app.models.cheat_code import (
    CheatCodeCategory,
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeRun,
    Recommendation,
    RunStatus,
)
from app.models.consent import ConsentRecord, ConsentType
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.goal import Goal, GoalType
from app.models.onboarding import OnboardingState, OnboardingStep
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.transaction import Transaction, TransactionType
from app.models.user import User, UserStatus
from app.services import (
    audit_service,
    consent_service,
    delete_service,
    export_service,
    ranking_service,
    vault_service,
)
from app.services.storage import InMemoryStorageBackend, get_storage, set_storage

# Standard steps payload for CheatCodeDefinition (required NOT NULL JSON field)
_DEFAULT_STEPS = [{"step_number": 1, "title": "Do it", "description": "Just do it", "estimated_minutes": 5}]


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield backend
    set_storage(None)


async def _create_user(db: AsyncSession, email: str = "trust@test.com") -> User:
    user = User(email=email, password_hash="hashed_pw")
    db.add(user)
    await db.flush()
    return user


async def _build_rich_user(db: AsyncSession, user: User) -> dict:
    """Create a user with entities across all phases for comprehensive testing."""
    entities = {}

    # Phase 0: Consent
    consent = ConsentRecord(
        user_id=user.id,
        consent_type=ConsentType.data_access,
        granted=True,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )
    db.add(consent)
    await db.flush()
    entities["consent"] = consent

    # Phase 1: Account + Transaction + Recurring
    account = Account(
        user_id=user.id,
        institution_name="Test Bank",
        account_name="Checking",
        account_type="checking",
        currency="USD",
    )
    db.add(account)
    await db.flush()
    entities["account"] = account

    txn = Transaction(
        account_id=account.id,
        user_id=user.id,
        raw_description="Netflix",
        normalized_description="netflix",
        amount=15.99,
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db.add(txn)
    await db.flush()
    entities["transaction"] = txn

    pattern = RecurringPattern(
        user_id=user.id,
        frequency=Frequency.monthly,
        confidence=Confidence.high,
        estimated_amount=Decimal("15.99"),
        label="Netflix subscription",
    )
    db.add(pattern)
    await db.flush()
    entities["pattern"] = pattern

    # Phase 2: Goal
    goal = Goal(
        user_id=user.id,
        title="Emergency fund",
        goal_type=GoalType.save_money,
        target_amount=Decimal("1000.00"),
    )
    db.add(goal)
    await db.flush()
    entities["goal"] = goal

    # Phase 4: Forecast
    forecast = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("250.00"),
        safe_to_spend_week=Decimal("500.00"),
        daily_balances=[],
        projected_end_balance=Decimal("200.00"),
        projected_end_low=Decimal("100.00"),
        projected_end_high=Decimal("300.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={"data_days": 45, "high_confidence_patterns": 1},
        assumptions=["1 recurring charge of $15.99"],
        urgency_score=30,
        urgency_factors={"spending_runway_days": 15},
    )
    db.add(forecast)
    await db.flush()
    entities["forecast"] = forecast

    # Phase 8: Vault
    vault_item = await vault_service.upload(
        db,
        user_id=user.id,
        filename="receipt.jpg",
        content_type="image/jpeg",
        data=b"fake receipt data",
        item_type="receipt",
        description="Lunch receipt",
        transaction_id=txn.id,
    )
    entities["vault_item"] = vault_item

    return entities


# ============================================================
# E2E Trust Test 1: Export completeness with real data
# ============================================================


@pytest.mark.asyncio
async def test_export_with_populated_data(db_session: AsyncSession):
    """Export with real entities has non-empty arrays for all populated types."""
    user = await _create_user(db_session)
    entities = await _build_rich_user(db_session, user)

    data = await export_service.export_user_data(db_session, user.id)

    # Core keys exist
    assert data["user"]["email"] == "trust@test.com"
    assert len(data["consent_records"]) >= 1
    assert len(data["accounts"]) >= 1
    assert len(data["transactions"]) >= 1
    assert len(data["recurring_patterns"]) >= 1
    assert len(data["goals"]) >= 1
    assert len(data["forecasts"]) >= 1
    assert len(data["vault_items"]) >= 1
    assert len(data["audit_log"]) >= 1  # at least the export event itself


@pytest.mark.asyncio
async def test_export_does_not_include_password(db_session: AsyncSession):
    """Export must NEVER include password hash."""
    user = await _create_user(db_session)
    data = await export_service.export_user_data(db_session, user.id)

    # User section should not have password_hash
    assert "password_hash" not in data["user"]
    assert "password" not in data["user"]

    # Full export string should not contain the actual hash
    export_str = str(data)
    assert "hashed_pw" not in export_str


@pytest.mark.asyncio
async def test_export_logs_audit_event(db_session: AsyncSession):
    """Export creates a user.data_exported audit event."""
    user = await _create_user(db_session)
    await export_service.export_user_data(db_session, user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "user.data_exported",
        )
    )
    event = result.scalar_one()
    assert event.action == "export"


# ============================================================
# E2E Trust Test 2: Delete purges PII + vault files
# ============================================================


@pytest.mark.asyncio
async def test_delete_purges_all_pii(db_session: AsyncSession):
    """After account deletion, no PII remains in user record."""
    user = await _create_user(db_session)
    entities = await _build_rich_user(db_session, user)
    user_id = user.id

    result = await delete_service.delete_user_data(db_session, user_id=user_id)
    assert result is True

    # User record: email anonymized, password cleared
    result = await db_session.execute(select(User).where(User.id == user_id))
    deleted_user = result.scalar_one()
    assert "trust@test.com" not in deleted_user.email
    assert deleted_user.email == f"deleted-{user_id}@deleted.local"
    assert deleted_user.password_hash == "DELETED"
    assert deleted_user.status == UserStatus.deleted
    assert deleted_user.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_purges_vault_storage(db_session: AsyncSession):
    """After deletion, vault files are removed from storage."""
    user = await _create_user(db_session)
    entities = await _build_rich_user(db_session, user)
    storage = get_storage()

    # Verify vault file exists before deletion
    vault_key = entities["vault_item"].storage_key
    assert await storage.exists(vault_key)

    await delete_service.delete_user_data(db_session, user_id=user.id)

    # Storage file must be gone
    assert not await storage.exists(vault_key)


@pytest.mark.asyncio
async def test_delete_purges_consent_records(db_session: AsyncSession):
    """After deletion, consent records are hard-deleted."""
    user = await _create_user(db_session)
    await _build_rich_user(db_session, user)

    await delete_service.delete_user_data(db_session, user_id=user.id)

    result = await db_session.execute(
        select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_delete_anonymizes_audit_trail(db_session: AsyncSession):
    """After deletion, audit trail PII is scrubbed but events remain."""
    user = await _create_user(db_session)
    await _build_rich_user(db_session, user)

    # Create an audit event with PII
    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="test.with_pii",
        entity_type="User",
        entity_id=user.id,
        action="test",
        detail={"email": "trust@test.com", "ip_address": "1.2.3.4", "some_key": "kept"},
        ip_address="1.2.3.4",
    )
    await db_session.flush()

    await delete_service.delete_user_data(db_session, user_id=user.id)

    # Audit events still exist (append-only)
    result = await db_session.execute(
        select(AuditLogEvent).where(AuditLogEvent.user_id == user.id)
    )
    events = result.scalars().all()
    assert len(events) > 0

    # PII scrubbed from detail and ip_address
    for event in events:
        assert event.ip_address is None
        if event.detail:
            assert "email" not in event.detail
            assert "ip_address" not in event.detail
            assert "user_agent" not in event.detail
            assert "password" not in event.detail


@pytest.mark.asyncio
async def test_delete_revokes_sessions(db_session: AsyncSession):
    """After deletion, all sessions are revoked."""
    from app.models.session import Session as SessionModel

    user = await _create_user(db_session)
    session = SessionModel(
        user_id=user.id,
        token="test_token_123",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(session)
    await db_session.flush()

    await delete_service.delete_user_data(db_session, user_id=user.id)

    result = await db_session.execute(
        select(SessionModel).where(SessionModel.user_id == user.id)
    )
    sessions = result.scalars().all()
    for s in sessions:
        assert s.revoked is True


# ============================================================
# E2E Trust Test 3: Audit trail reconstructs "why"
# ============================================================


@pytest.mark.asyncio
async def test_audit_trail_records_all_critical_actions(db_session: AsyncSession):
    """Critical actions (consent, vault upload, delete) all leave audit trails."""
    user = await _create_user(db_session)

    # 1. Consent action
    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )

    # 2. Vault upload
    await vault_service.upload(
        db_session,
        user_id=user.id,
        filename="audit_test.jpg",
        content_type="image/jpeg",
        data=b"data",
    )

    # Check audit trail
    result = await db_session.execute(
        select(AuditLogEvent)
        .where(AuditLogEvent.user_id == user.id)
        .order_by(AuditLogEvent.timestamp.asc())
    )
    events = result.scalars().all()
    event_types = [e.event_type for e in events]

    assert "consent.granted" in event_types
    assert "vault.uploaded" in event_types

    # All events have required fields
    for event in events:
        assert event.user_id == user.id
        assert event.event_type is not None
        assert event.timestamp is not None


@pytest.mark.asyncio
async def test_audit_reconstruct_why_function(db_session: AsyncSession):
    """audit_service.reconstruct_why returns full action history for an entity."""
    user = await _create_user(db_session)

    # Create audit events for a specific entity
    entity_id = uuid.uuid4()
    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="entity.created",
        entity_type="TestEntity",
        entity_id=entity_id,
        action="create",
        detail={"reason": "user_requested"},
    )
    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="entity.modified",
        entity_type="TestEntity",
        entity_id=entity_id,
        action="update",
        detail={"field": "status", "old": "draft", "new": "active"},
    )
    await db_session.flush()

    events = await audit_service.reconstruct_why(
        db_session, entity_type="TestEntity", entity_id=entity_id
    )
    assert len(events) == 2
    assert events[0].action == "create"
    assert events[1].action == "update"


# ============================================================
# E2E Trust Test 4: Low confidence never in Top 3
# ============================================================


@pytest.mark.asyncio
async def test_top3_no_low_confidence_with_only_low_data(db_session: AsyncSession):
    """Even when all available data is low quality, Top 3 never has low confidence."""
    user = await _create_user(db_session)

    # Create cheat codes
    for i in range(5):
        db_session.add(CheatCodeDefinition(
            code=f"CC-LOW{i}",
            title=f"Low Data Test {i}",
            description="Test",
            category=CheatCodeCategory.save_money,
            difficulty=CheatCodeDifficulty.quick_win if i == 0 else CheatCodeDifficulty.medium,
            estimated_minutes=5 if i == 0 else 30,
            steps=_DEFAULT_STEPS,
            potential_savings_min=Decimal("1"),
            potential_savings_max=Decimal("5"),
        ))
    await db_session.flush()

    # No goals, no patterns, no forecast — minimum data
    recommendations = await ranking_service.compute_top_3(db_session, user.id)

    for rec in recommendations:
        assert rec.confidence != "low", (
            f"Low confidence found in Top 3 — PRD violation! "
            f"rank={rec.rank}, confidence={rec.confidence}"
        )


@pytest.mark.asyncio
async def test_top3_no_low_confidence_with_max_urgency(db_session: AsyncSession):
    """Max urgency cannot force low confidence into Top 3."""
    user = await _create_user(db_session)

    for i in range(4):
        db_session.add(CheatCodeDefinition(
            code=f"CC-MU{i}",
            title=f"Max Urgency {i}",
            description="Test",
            category=CheatCodeCategory.reduce_spending,
            difficulty=CheatCodeDifficulty.quick_win if i == 0 else CheatCodeDifficulty.medium,
            estimated_minutes=5 if i == 0 else 30,
            steps=_DEFAULT_STEPS,
            potential_savings_min=Decimal("10"),
            potential_savings_max=Decimal("100"),
        ))
    await db_session.flush()

    # Max urgency forecast
    db_session.add(ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("-1000.00"),
        safe_to_spend_week=Decimal("-5000.00"),
        daily_balances=[],
        projected_end_balance=Decimal("-8000.00"),
        projected_end_low=Decimal("-10000.00"),
        projected_end_high=Decimal("-6000.00"),
        confidence=ForecastConfidence.low,
        confidence_inputs={"data_days": 5, "high_confidence_patterns": 0},
        assumptions=["Insufficient data"],
        urgency_score=100,
        urgency_factors={"negative_sts": True, "spending_runway_days": 0},
    ))
    await db_session.flush()

    recommendations = await ranking_service.compute_top_3(db_session, user.id)
    for rec in recommendations:
        assert rec.confidence != "low"


# ============================================================
# E2E Trust Test 5: First Win hard gate
# ============================================================


@pytest.mark.asyncio
async def test_first_win_requires_completed_step(db_session: AsyncSession):
    """First Win gate cannot be passed without completing a cheat code step."""
    from app.services import onboarding_service

    user = await _create_user(db_session)
    await onboarding_service.get_or_create_state(db_session, user_id=user.id)

    # Advance through consent → account_link → goals → top_3
    for step in [
        OnboardingStep.consent,
        OnboardingStep.account_link,
        OnboardingStep.goals,
        OnboardingStep.top_3,
    ]:
        await onboarding_service.advance_step(
            db_session, user_id=user.id, completed_step=step
        )

    # Try to advance to first_win without completing a cheat code step
    with pytest.raises(ValueError):
        await onboarding_service.advance_step(
            db_session, user_id=user.id, completed_step=OnboardingStep.first_win
        )


# ============================================================
# E2E Trust Test 6: Delete via API purges vault (integration)
# ============================================================


@pytest.mark.asyncio
async def test_delete_via_api_purges_vault(
    client: AsyncClient, db_session: AsyncSession
):
    """DELETE /user/delete purges vault items and storage files."""
    storage = get_storage()

    # Register and login
    await client.post(
        "/auth/register",
        json={"email": "deleteme@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "deleteme@test.com", "password": "SecurePass123!"},
    )
    headers = {"X-Session-Token": resp.json()["token"]}

    # Upload vault items
    for name in ("a.jpg", "b.png"):
        ct = "image/jpeg" if name.endswith(".jpg") else "image/png"
        files = {"file": (name, io.BytesIO(b"vault data"), ct)}
        resp = await client.post(
            "/vault", headers=headers, files=files,
            data={"item_type": "receipt"},
        )
        assert resp.status_code == 201

    # Verify 2 items in vault
    resp = await client.get("/vault", headers=headers)
    assert len(resp.json()) == 2

    # Delete account
    resp = await client.delete("/user/delete", headers=headers)
    assert resp.status_code == 204

    # All storage files cleaned
    assert len(storage._store) == 0
