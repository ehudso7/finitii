"""Phase 0 end-to-end integration test.

Full lifecycle: register -> login -> grant consent -> verify AI memory off by default
-> revoke consent -> export (includes all records) -> delete (PII gone, audit retained)
-> verify cannot login.

This test runs the entire Phase 0 lifecycle without manual intervention.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.models.consent import ConsentRecord
from app.models.user import User, UserStatus


@pytest.mark.asyncio
async def test_full_phase0_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """End-to-end Phase 0 lifecycle test."""

    # ──────────────────────────────────────────────────────────
    # Step 1: Register
    # ──────────────────────────────────────────────────────────
    register_resp = await client.post(
        "/auth/register",
        json={"email": "e2e@example.com", "password": "SecurePass123!"},
    )
    assert register_resp.status_code == 201
    user_data = register_resp.json()
    user_id = user_data["id"]
    assert user_data["email"] == "e2e@example.com"
    assert user_data["status"] == "active"

    # ──────────────────────────────────────────────────────────
    # Step 2: Login
    # ──────────────────────────────────────────────────────────
    login_resp = await client.post(
        "/auth/login",
        json={"email": "e2e@example.com", "password": "SecurePass123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    headers = {"X-Session-Token": token}

    # ──────────────────────────────────────────────────────────
    # Step 3: Verify AI memory off by default
    # ──────────────────────────────────────────────────────────
    status_resp = await client.get("/consent/status", headers=headers)
    assert status_resp.status_code == 200
    consents = status_resp.json()["consents"]
    assert consents["ai_memory"] is False
    assert consents["data_access"] is False
    assert consents["terms_of_service"] is False

    # ──────────────────────────────────────────────────────────
    # Step 4: Grant consent (data_access + terms_of_service)
    # ──────────────────────────────────────────────────────────
    grant_resp = await client.post(
        "/consent/grant",
        json={"consent_type": "data_access"},
        headers=headers,
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["granted"] is True

    grant_resp2 = await client.post(
        "/consent/grant",
        json={"consent_type": "terms_of_service"},
        headers=headers,
    )
    assert grant_resp2.status_code == 200

    # Verify status updated
    status_resp = await client.get("/consent/status", headers=headers)
    consents = status_resp.json()["consents"]
    assert consents["data_access"] is True
    assert consents["terms_of_service"] is True
    assert consents["ai_memory"] is False  # Still off

    # ──────────────────────────────────────────────────────────
    # Step 5: Revoke consent (data_access)
    # ──────────────────────────────────────────────────────────
    revoke_resp = await client.post(
        "/consent/revoke",
        json={"consent_type": "data_access"},
        headers=headers,
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["granted"] is False

    status_resp = await client.get("/consent/status", headers=headers)
    consents = status_resp.json()["consents"]
    assert consents["data_access"] is False

    # ──────────────────────────────────────────────────────────
    # Step 6: Export data
    # ──────────────────────────────────────────────────────────
    export_resp = await client.get("/user/export", headers=headers)
    assert export_resp.status_code == 200
    export_data = export_resp.json()

    # Verify export structure
    assert "user" in export_data
    assert "consent_records" in export_data
    assert "audit_log" in export_data

    # Verify user data in export
    assert export_data["user"]["email"] == "e2e@example.com"
    assert export_data["user"]["status"] == "active"

    # Verify consent records in export (2 grants: data_access + terms_of_service)
    assert len(export_data["consent_records"]) == 2

    # Verify audit log has events (register, login, consent grants, revoke, etc.)
    audit_events = export_data["audit_log"]
    event_types = [e["event_type"] for e in audit_events]
    assert "auth.register" in event_types
    assert "auth.login" in event_types
    assert "consent.granted" in event_types
    assert "consent.revoked" in event_types

    # ──────────────────────────────────────────────────────────
    # Step 7: Delete account
    # ──────────────────────────────────────────────────────────
    delete_resp = await client.delete("/user/delete", headers=headers)
    assert delete_resp.status_code == 204

    # ──────────────────────────────────────────────────────────
    # Step 8: Verify cannot login after deletion
    # ──────────────────────────────────────────────────────────
    login_resp = await client.post(
        "/auth/login",
        json={"email": "e2e@example.com", "password": "SecurePass123!"},
    )
    # Should fail — either 401 (email no longer matches) or 403 (account inactive)
    assert login_resp.status_code in (401, 403)

    # ──────────────────────────────────────────────────────────
    # Step 9: Verify PII is gone but audit trail retained
    # ──────────────────────────────────────────────────────────
    # Check user record directly — query by deleted status (only one user in test DB)
    result = await db_session.execute(select(User).where(User.status == UserStatus.deleted))
    deleted_user = result.scalar_one_or_none()
    assert deleted_user is not None
    assert deleted_user.email != "e2e@example.com"  # PII gone
    assert "deleted" in deleted_user.email
    assert deleted_user.password_hash == "DELETED"
    assert deleted_user.deleted_at is not None

    # Consent records should be gone
    result = await db_session.execute(
        select(ConsentRecord).where(ConsentRecord.user_id == deleted_user.id)
    )
    assert result.scalars().all() == []

    # Audit trail retained but anonymized
    result = await db_session.execute(
        select(AuditLogEvent).where(AuditLogEvent.user_id == deleted_user.id)
    )
    events = result.scalars().all()
    assert len(events) >= 5  # register, login, consents, revoke, export, delete

    for event in events:
        assert event.ip_address is None  # IP scrubbed
        if event.detail:
            assert "email" not in event.detail  # email PII scrubbed
