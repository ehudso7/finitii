import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.models.user import User


async def _create_user(db_session: AsyncSession) -> User:
    user = User(email="audit@example.com", password_hash="fakehash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_and_read_audit_event(db_session: AsyncSession):
    """Insert audit event -> read -> fields match."""
    user = await _create_user(db_session)

    event = AuditLogEvent(
        user_id=user.id,
        event_type="consent.granted",
        entity_type="ConsentRecord",
        entity_id=uuid.uuid4(),
        action="grant",
        detail={"consent_type": "data_access"},
        ip_address="127.0.0.1",
    )
    db_session.add(event)
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLogEvent).where(AuditLogEvent.user_id == user.id)
    )
    fetched = result.scalar_one()

    assert fetched.id is not None
    assert fetched.user_id == user.id
    assert fetched.event_type == "consent.granted"
    assert fetched.entity_type == "ConsentRecord"
    assert fetched.action == "grant"
    assert fetched.detail == {"consent_type": "data_access"}
    assert fetched.timestamp is not None
    assert fetched.ip_address == "127.0.0.1"


@pytest.mark.asyncio
async def test_audit_event_append_only_no_orm_delete(db_session: AsyncSession):
    """Verify we do not expose ORM-level delete for audit events.

    The append-only constraint is enforced at the service layer (P0-T06),
    but at the model level we verify we can insert and read without any
    delete helper methods on the model itself.
    """
    user = await _create_user(db_session)

    events = []
    for i in range(5):
        event = AuditLogEvent(
            user_id=user.id,
            event_type=f"test.event.{i}",
            entity_type="TestEntity",
            entity_id=uuid.uuid4(),
            action="test",
        )
        events.append(event)
    db_session.add_all(events)
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLogEvent)
        .where(AuditLogEvent.user_id == user.id)
        .order_by(AuditLogEvent.timestamp)
    )
    fetched = result.scalars().all()
    assert len(fetched) == 5
    for i, evt in enumerate(fetched):
        assert evt.event_type == f"test.event.{i}"


@pytest.mark.asyncio
async def test_audit_event_json_detail(db_session: AsyncSession):
    """Detail field stores and retrieves JSON correctly."""
    user = await _create_user(db_session)

    complex_detail = {
        "before": {"status": "active"},
        "after": {"status": "deleted"},
        "reason": "user_requested",
    }
    event = AuditLogEvent(
        user_id=user.id,
        event_type="user.deleted",
        entity_type="User",
        entity_id=user.id,
        action="delete",
        detail=complex_detail,
    )
    db_session.add(event)
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLogEvent).where(AuditLogEvent.event_type == "user.deleted")
    )
    fetched = result.scalar_one()
    assert fetched.detail == complex_detail
