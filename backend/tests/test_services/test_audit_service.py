import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import audit_service


async def _create_user(db_session: AsyncSession) -> User:
    user = User(email="audit-svc@example.com", password_hash="fakehash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_log_event(db_session: AsyncSession):
    """log_event creates an audit event."""
    user = await _create_user(db_session)
    entity_id = uuid.uuid4()

    event = await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="test.created",
        entity_type="TestEntity",
        entity_id=entity_id,
        action="create",
        detail={"key": "value"},
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    assert event.id is not None
    assert event.user_id == user.id
    assert event.event_type == "test.created"
    assert event.detail == {"key": "value"}


@pytest.mark.asyncio
async def test_get_events_for_user_returns_all(db_session: AsyncSession):
    """Log 5 events -> retrieve by user -> all 5 returned in order."""
    user = await _create_user(db_session)

    for i in range(5):
        await audit_service.log_event(
            db_session,
            user_id=user.id,
            event_type=f"test.event.{i}",
            entity_type="TestEntity",
            entity_id=uuid.uuid4(),
            action="test",
        )
    await db_session.commit()

    events = await audit_service.get_events_for_user(db_session, user.id)
    assert len(events) == 5
    for i, evt in enumerate(events):
        assert evt.event_type == f"test.event.{i}"


@pytest.mark.asyncio
async def test_get_events_with_filters(db_session: AsyncSession):
    """Filter by event_type and entity_type."""
    user = await _create_user(db_session)

    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="consent.granted",
        entity_type="ConsentRecord",
        entity_id=uuid.uuid4(),
        action="grant",
    )
    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="user.login",
        entity_type="User",
        entity_id=user.id,
        action="login",
    )
    await db_session.commit()

    consent_events = await audit_service.get_events_for_user(
        db_session, user.id, event_type="consent.granted"
    )
    assert len(consent_events) == 1
    assert consent_events[0].event_type == "consent.granted"

    user_events = await audit_service.get_events_for_user(
        db_session, user.id, entity_type="User"
    )
    assert len(user_events) == 1


@pytest.mark.asyncio
async def test_reconstruct_why(db_session: AsyncSession):
    """reconstruct_why returns the chain of events for a given entity."""
    user = await _create_user(db_session)
    entity_id = uuid.uuid4()

    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="consent.granted",
        entity_type="ConsentRecord",
        entity_id=entity_id,
        action="grant",
        detail={"consent_type": "data_access"},
    )
    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="consent.revoked",
        entity_type="ConsentRecord",
        entity_id=entity_id,
        action="revoke",
        detail={"consent_type": "data_access"},
    )
    # Unrelated event for a different entity
    await audit_service.log_event(
        db_session,
        user_id=user.id,
        event_type="user.login",
        entity_type="User",
        entity_id=user.id,
        action="login",
    )
    await db_session.commit()

    chain = await audit_service.reconstruct_why(db_session, "ConsentRecord", entity_id)
    assert len(chain) == 2
    assert chain[0].action == "grant"
    assert chain[1].action == "revoke"


@pytest.mark.asyncio
async def test_no_delete_pathway(db_session: AsyncSession):
    """Verify the audit_service module has no delete function."""
    public_functions = [name for name in dir(audit_service) if not name.startswith("_")]
    for name in public_functions:
        assert "delete" not in name.lower(), f"Found delete pathway: {name}"
