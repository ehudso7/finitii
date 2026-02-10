"""Export service: export all user data as a JSON bundle.

Must include: user profile, consent records, audit log, and all future entities
as they're added in later phases.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.models.consent import ConsentRecord
from app.models.user import User
from app.services import audit_service


def _serialize_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _serialize_uuid(u: uuid.UUID | None) -> str | None:
    if u is None:
        return None
    return str(u)


async def export_user_data(
    db: AsyncSession,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Export ALL user data as a JSON-serializable dict.

    Includes user profile, consent records, and audit log.
    Future phases will add additional entities here as they are implemented.
    """
    # User profile
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return {"error": "User not found"}

    user_data = {
        "id": _serialize_uuid(user.id),
        "email": user.email,
        "status": user.status.value,
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
            "consent_type": c.consent_type.value,
            "granted": c.granted,
            "granted_at": _serialize_datetime(c.granted_at),
            "revoked_at": _serialize_datetime(c.revoked_at),
            "ip_address": c.ip_address,
            "user_agent": c.user_agent,
        }
        for c in consent_records
    ]

    # Audit log
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
        "audit_log": audit_data,
    }
