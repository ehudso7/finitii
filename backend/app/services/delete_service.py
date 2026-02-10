"""Delete service: soft-delete user, hard-delete PII, retain anonymized audit trail.

Per PRD:
- User marked as deleted
- All PII hard-deleted
- Audit trail retained but anonymized (user_id preserved for chain, PII in detail scrubbed)
- Vault items fully deleted (enforced when Vault exists in Phase 8)
- Sessions revoked
- Consent records deleted (PII)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.models.consent import ConsentRecord
from app.models.session import Session
from app.models.user import User, UserStatus
from app.services import audit_service

# PII fields in audit detail that must be scrubbed
_PII_DETAIL_KEYS = {"email", "ip_address", "user_agent", "password"}


def _anonymize_detail(detail: dict | None) -> dict | None:
    """Remove PII keys from audit event detail."""
    if detail is None:
        return None
    return {k: v for k, v in detail.items() if k not in _PII_DETAIL_KEYS}


async def delete_user_data(
    db: AsyncSession,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> bool:
    """Delete user data per PRD requirements.

    Returns True if user was found and deleted, False if not found.
    """
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return False

    # 1. Log deletion event BEFORE we anonymize (so it captures the action)
    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="user.data_deleted",
        entity_type="User",
        entity_id=user_id,
        action="delete",
        detail={"reason": "user_requested"},
        ip_address=ip_address,
    )

    # 2. Revoke all sessions
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id)
        .values(revoked=True)
    )

    # 3. Hard-delete consent records (PII)
    await db.execute(
        delete(ConsentRecord).where(ConsentRecord.user_id == user_id)
    )

    # 4. Anonymize audit trail: scrub PII from detail, clear ip_address
    result = await db.execute(
        select(AuditLogEvent).where(AuditLogEvent.user_id == user_id)
    )
    audit_events = result.scalars().all()
    for event in audit_events:
        event.detail = _anonymize_detail(event.detail)
        event.ip_address = None

    # 5. Soft-delete user: clear PII, mark as deleted
    user.email = f"deleted-{user_id}@deleted.local"
    user.password_hash = "DELETED"
    user.status = UserStatus.deleted
    user.deleted_at = datetime.now(timezone.utc)

    await db.flush()
    return True
