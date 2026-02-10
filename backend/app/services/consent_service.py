"""Consent service: grant, revoke, check, list consents.

Every consent change is logged to the audit log.
AI memory consent defaults to OFF (not granted) — must be explicitly granted.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentRecord, ConsentType
from app.services import audit_service


async def grant_consent(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    consent_type: ConsentType,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ConsentRecord:
    """Grant a consent. Creates a new ConsentRecord and logs to audit."""
    # Check if there's an existing active consent of this type
    existing = await _get_active_consent(db, user_id, consent_type)
    if existing is not None:
        # Already granted — return existing
        return existing

    consent = ConsentRecord(
        user_id=user_id,
        consent_type=consent_type,
        granted=True,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(consent)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="consent.granted",
        entity_type="ConsentRecord",
        entity_id=consent.id,
        action="grant",
        detail={"consent_type": consent_type.value},
        ip_address=ip_address,
    )

    return consent


async def revoke_consent(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    consent_type: ConsentType,
    ip_address: str | None = None,
) -> ConsentRecord | None:
    """Revoke a consent. Sets revoked_at and granted=False, logs to audit.

    Returns the updated ConsentRecord, or None if no active consent found.
    """
    consent = await _get_active_consent(db, user_id, consent_type)
    if consent is None:
        return None

    consent.granted = False
    consent.revoked_at = datetime.now(timezone.utc)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="consent.revoked",
        entity_type="ConsentRecord",
        entity_id=consent.id,
        action="revoke",
        detail={"consent_type": consent_type.value},
        ip_address=ip_address,
    )

    return consent


async def check_consent(
    db: AsyncSession,
    user_id: uuid.UUID,
    consent_type: ConsentType,
) -> bool:
    """Check if a specific consent is currently active (granted and not revoked)."""
    consent = await _get_active_consent(db, user_id, consent_type)
    return consent is not None


async def get_all_consents(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[ConsentRecord]:
    """Return all consent records for a user (including revoked)."""
    stmt = (
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id)
        .order_by(ConsentRecord.granted_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_active_consent(
    db: AsyncSession,
    user_id: uuid.UUID,
    consent_type: ConsentType,
) -> ConsentRecord | None:
    """Find the currently active (granted=True, not revoked) consent of a given type."""
    stmt = select(ConsentRecord).where(
        ConsentRecord.user_id == user_id,
        ConsentRecord.consent_type == consent_type,
        ConsentRecord.granted == True,  # noqa: E712
        ConsentRecord.revoked_at == None,  # noqa: E711
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
