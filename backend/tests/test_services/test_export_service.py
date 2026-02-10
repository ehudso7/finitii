import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import register_user
from app.models.consent import ConsentType
from app.services import audit_service, consent_service, export_service


@pytest.mark.asyncio
async def test_export_contains_all_data(db_session: AsyncSession):
    """Create user with consent records + audit events -> export -> JSON contains all data."""
    # Register user (creates audit event)
    user = await register_user(
        db_session, email="export@example.com", password="Pass123!", ip_address="10.0.0.1"
    )
    await db_session.commit()

    # Grant consent (creates audit event)
    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    # Export
    data = await export_service.export_user_data(db_session, user.id, ip_address="10.0.0.1")
    await db_session.commit()

    # Verify structure
    assert "user" in data
    assert "consent_records" in data
    assert "audit_log" in data

    # Verify user data
    assert data["user"]["email"] == "export@example.com"
    assert data["user"]["status"] == "active"

    # Verify consent records
    assert len(data["consent_records"]) == 1
    assert data["consent_records"][0]["consent_type"] == "data_access"
    assert data["consent_records"][0]["granted"] is True

    # Verify audit log contains events (register + consent.granted, NOT the export event
    # since it's logged after the read)
    assert len(data["audit_log"]) >= 2
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
