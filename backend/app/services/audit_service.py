"""Audit service: append-only event logging and reconstruction.

All writes are append-only. No update or delete methods are exposed.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent


async def log_event(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> AuditLogEvent:
    """Create an append-only audit log event."""
    event = AuditLogEvent(
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(event)
    await db.flush()
    return event


async def get_events_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    event_type: str | None = None,
    entity_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLogEvent]:
    """Retrieve audit events for a user, with optional filters."""
    stmt = (
        select(AuditLogEvent)
        .where(AuditLogEvent.user_id == user_id)
        .order_by(AuditLogEvent.timestamp.asc())
    )
    if event_type is not None:
        stmt = stmt.where(AuditLogEvent.event_type == event_type)
    if entity_type is not None:
        stmt = stmt.where(AuditLogEvent.entity_type == entity_type)
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def reconstruct_why(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
) -> list[AuditLogEvent]:
    """Return the chain of audit events explaining 'why' for a given entity.

    Returns all events related to the specified entity, ordered chronologically.
    This allows reconstructing the full decision/action history.
    """
    stmt = (
        select(AuditLogEvent)
        .where(
            AuditLogEvent.entity_type == entity_type,
            AuditLogEvent.entity_id == entity_id,
        )
        .order_by(AuditLogEvent.timestamp.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
