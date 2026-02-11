"""Export service: export all user data as a JSON bundle.

Must include: user profile, consent records, audit log, and all user-owned entities.
Phase 9: Updated to include all entities from Phases 0-8 for data subject access completeness.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.audit import AuditLogEvent
from app.models.cheat_code import CheatCodeOutcome, CheatCodeRun, Recommendation
from app.models.coach_memory import CoachMemory
from app.models.consent import ConsentRecord
from app.models.forecast import ForecastSnapshot
from app.models.goal import Goal, UserConstraint
from app.models.learn import LessonProgress
from app.models.onboarding import OnboardingState
from app.models.practice import ScenarioRun
from app.models.recurring import RecurringPattern
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vault import VaultItem
from app.services import audit_service


def _serialize_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _serialize_uuid(u: uuid.UUID | None) -> str | None:
    if u is None:
        return None
    return str(u)


def _serialize_decimal(d: Decimal | None) -> str | None:
    if d is None:
        return None
    return str(d)


def _serialize_enum(val) -> str | None:
    """Extract string value from an enum or pass through a raw string.

    SQLAlchemy with native_enum=False may return raw strings from the DB
    instead of reconstructing the Python enum, depending on session state.
    """
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


async def export_user_data(
    db: AsyncSession,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Export ALL user data as a JSON-serializable dict.

    Includes all user-owned entities across Phases 0-8.
    """
    # User profile
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return {"error": "User not found"}

    user_data = {
        "id": _serialize_uuid(user.id),
        "email": user.email,
        "status": _serialize_enum(user.status),
        "created_at": _serialize_datetime(user.created_at),
        "updated_at": _serialize_datetime(user.updated_at),
        "deleted_at": _serialize_datetime(user.deleted_at),
    }

    # Consent records
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id)
        .order_by(ConsentRecord.granted_at.asc())
    )
    consent_records = result.scalars().all()
    consent_data = [
        {
            "id": _serialize_uuid(c.id),
            "consent_type": _serialize_enum(c.consent_type),
            "granted": c.granted,
            "granted_at": _serialize_datetime(c.granted_at),
            "revoked_at": _serialize_datetime(c.revoked_at),
            "ip_address": c.ip_address,
            "user_agent": c.user_agent,
        }
        for c in consent_records
    ]

    # Accounts (Phase 1)
    result = await db.execute(
        select(Account).where(Account.user_id == user_id)
    )
    accounts_data = [
        {
            "id": _serialize_uuid(a.id),
            "institution_name": a.institution_name,
            "account_name": a.account_name,
            "account_type": _serialize_enum(a.account_type),
            "currency": a.currency,
        }
        for a in result.scalars().all()
    ]

    # Transactions (Phase 1)
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.asc())
    )
    transactions_data = [
        {
            "id": _serialize_uuid(t.id),
            "account_id": _serialize_uuid(t.account_id),
            "amount": _serialize_decimal(t.amount),
            "currency": t.currency,
            "transaction_date": _serialize_datetime(t.transaction_date),
            "transaction_type": _serialize_enum(t.transaction_type),
            "normalized_description": t.normalized_description,
        }
        for t in result.scalars().all()
    ]

    # Recurring patterns (Phase 1)
    result = await db.execute(
        select(RecurringPattern).where(RecurringPattern.user_id == user_id)
    )
    recurring_data = [
        {
            "id": _serialize_uuid(r.id),
            "frequency": _serialize_enum(r.frequency),
            "confidence": _serialize_enum(r.confidence),
            "estimated_amount": _serialize_decimal(r.estimated_amount),
            "is_active": r.is_active,
            "is_manual": r.is_manual,
            "is_essential": r.is_essential,
            "label": r.label,
        }
        for r in result.scalars().all()
    ]

    # Goals (Phase 2)
    result = await db.execute(
        select(Goal).where(Goal.user_id == user_id)
    )
    goals_data = [
        {
            "id": _serialize_uuid(g.id),
            "title": g.title,
            "goal_type": _serialize_enum(g.goal_type),
            "target_amount": _serialize_decimal(g.target_amount),
            "is_active": g.is_active,
        }
        for g in result.scalars().all()
    ]

    # User constraints (Phase 2)
    result = await db.execute(
        select(UserConstraint).where(UserConstraint.user_id == user_id)
    )
    constraints_data = [
        {
            "id": _serialize_uuid(uc.id),
            "constraint_type": uc.constraint_type,
            "label": uc.label,
            "amount": str(uc.amount) if uc.amount is not None else None,
            "notes": uc.notes,
        }
        for uc in result.scalars().all()
    ]

    # Onboarding state (Phase 2)
    result = await db.execute(
        select(OnboardingState).where(OnboardingState.user_id == user_id)
    )
    onboarding = result.scalar_one_or_none()
    onboarding_data = None
    if onboarding:
        onboarding_data = {
            "current_step": _serialize_enum(onboarding.current_step),
            "consent_completed_at": onboarding.consent_completed_at.isoformat() if onboarding.consent_completed_at else None,
            "account_completed_at": onboarding.account_completed_at.isoformat() if onboarding.account_completed_at else None,
            "goals_completed_at": onboarding.goals_completed_at.isoformat() if onboarding.goals_completed_at else None,
            "top_3_completed_at": onboarding.top_3_completed_at.isoformat() if onboarding.top_3_completed_at else None,
            "first_win_completed_at": onboarding.first_win_completed_at.isoformat() if onboarding.first_win_completed_at else None,
        }

    # Recommendations (Phase 3)
    result = await db.execute(
        select(Recommendation).where(Recommendation.user_id == user_id)
    )
    recommendations_data = [
        {
            "id": _serialize_uuid(r.id),
            "cheat_code_id": _serialize_uuid(r.cheat_code_id),
            "rank": r.rank,
            "confidence": r.confidence,
            "explanation": r.explanation,
        }
        for r in result.scalars().all()
    ]

    # Cheat code runs (Phase 3)
    result = await db.execute(
        select(CheatCodeRun).where(CheatCodeRun.user_id == user_id)
    )
    runs_data = [
        {
            "id": _serialize_uuid(r.id),
            "cheat_code_id": _serialize_uuid(r.cheat_code_id),
            "status": _serialize_enum(r.status),
            "started_at": _serialize_datetime(r.started_at),
            "completed_at": _serialize_datetime(r.completed_at),
        }
        for r in result.scalars().all()
    ]

    # Cheat code outcomes (Phase 3)
    result = await db.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.user_id == user_id)
    )
    outcomes_data = [
        {
            "id": _serialize_uuid(o.id),
            "run_id": _serialize_uuid(o.run_id),
            "reported_savings": _serialize_decimal(o.reported_savings),
        }
        for o in result.scalars().all()
    ]

    # Forecast snapshots (Phase 4)
    result = await db.execute(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.user_id == user_id)
        .order_by(ForecastSnapshot.computed_at.desc())
    )
    forecasts_data = [
        {
            "id": _serialize_uuid(f.id),
            "safe_to_spend_today": _serialize_decimal(f.safe_to_spend_today),
            "safe_to_spend_week": _serialize_decimal(f.safe_to_spend_week),
            "confidence": _serialize_enum(f.confidence),
            "urgency_score": f.urgency_score,
            "computed_at": _serialize_datetime(f.computed_at),
        }
        for f in result.scalars().all()
    ]

    # Coach memory (Phase 6)
    result = await db.execute(
        select(CoachMemory).where(CoachMemory.user_id == user_id)
    )
    coach_memory = result.scalar_one_or_none()
    coach_memory_data = None
    if coach_memory:
        coach_memory_data = {
            "tone": _serialize_enum(coach_memory.tone),
            "aggressiveness": _serialize_enum(coach_memory.aggressiveness),
        }

    # Lesson progress (Phase 7)
    result = await db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user_id)
    )
    lesson_progress_data = [
        {
            "id": _serialize_uuid(lp.id),
            "lesson_id": _serialize_uuid(lp.lesson_id),
            "status": _serialize_enum(lp.status),
            "completed_sections": lp.completed_sections,
        }
        for lp in result.scalars().all()
    ]

    # Scenario runs (Phase 7)
    result = await db.execute(
        select(ScenarioRun).where(ScenarioRun.user_id == user_id)
    )
    scenario_runs_data = [
        {
            "id": _serialize_uuid(sr.id),
            "scenario_id": _serialize_uuid(sr.scenario_id),
            "status": _serialize_enum(sr.status),
            "confidence": sr.confidence,
            "plan_generated": sr.plan_generated,
        }
        for sr in result.scalars().all()
    ]

    # Vault items (Phase 8) — metadata only, no file content
    result = await db.execute(
        select(VaultItem).where(VaultItem.user_id == user_id)
    )
    vault_data = [
        {
            "id": _serialize_uuid(v.id),
            "filename": v.filename,
            "content_type": v.content_type,
            "file_size": v.file_size,
            "item_type": _serialize_enum(v.item_type),
            "description": v.description,
            "transaction_id": _serialize_uuid(v.transaction_id),
            "uploaded_at": _serialize_datetime(v.uploaded_at),
        }
        for v in result.scalars().all()
    ]

    # Audit log (always last — most complete)
    result = await db.execute(
        select(AuditLogEvent)
        .where(AuditLogEvent.user_id == user_id)
        .order_by(AuditLogEvent.timestamp.asc())
    )
    audit_events = result.scalars().all()
    audit_data = [
        {
            "id": _serialize_uuid(e.id),
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": _serialize_uuid(e.entity_id),
            "action": e.action,
            "detail": e.detail,
            "timestamp": _serialize_datetime(e.timestamp),
            "ip_address": e.ip_address,
        }
        for e in audit_events
    ]

    # Log the export event itself
    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="user.data_exported",
        entity_type="User",
        entity_id=user_id,
        action="export",
        ip_address=ip_address,
    )

    return {
        "user": user_data,
        "consent_records": consent_data,
        "accounts": accounts_data,
        "transactions": transactions_data,
        "recurring_patterns": recurring_data,
        "goals": goals_data,
        "constraints": constraints_data,
        "onboarding": onboarding_data,
        "recommendations": recommendations_data,
        "cheat_code_runs": runs_data,
        "cheat_code_outcomes": outcomes_data,
        "forecasts": forecasts_data,
        "coach_memory": coach_memory_data,
        "lesson_progress": lesson_progress_data,
        "scenario_runs": scenario_runs_data,
        "vault_items": vault_data,
        "audit_log": audit_data,
    }
