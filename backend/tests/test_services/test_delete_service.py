import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import login_user, register_user
from app.models.audit import AuditLogEvent
from app.models.consent import ConsentRecord, ConsentType
from app.models.session import Session
from app.models.user import User, UserStatus
from app.services import consent_service, delete_service


@pytest.mark.asyncio
async def test_delete_user_marks_deleted(db_session: AsyncSession):
    """User marked deleted after deletion."""
    user = await register_user(
        db_session, email="del@example.com", password="Pass123!"
    )
    await db_session.commit()

    result = await delete_service.delete_user_data(db_session, user.id)
    await db_session.commit()
    assert result is True

    fetched = await db_session.execute(select(User).where(User.id == user.id))
    u = fetched.scalar_one()
    assert u.status == UserStatus.deleted
    assert u.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_removes_pii(db_session: AsyncSession):
    """PII is gone after deletion: email replaced, password hash cleared."""
    user = await register_user(
        db_session, email="pii@example.com", password="Pass123!"
    )
    await db_session.commit()
    user_id = user.id

    await delete_service.delete_user_data(db_session, user_id)
    await db_session.commit()

    fetched = await db_session.execute(select(User).where(User.id == user_id))
    u = fetched.scalar_one()
    assert u.email != "pii@example.com"
    assert "deleted" in u.email
    assert u.password_hash == "DELETED"


@pytest.mark.asyncio
async def test_delete_removes_consent_records(db_session: AsyncSession):
    """Consent records hard-deleted after user deletion."""
    user = await register_user(
        db_session, email="consent-del@example.com", password="Pass123!"
    )
    await db_session.commit()

    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await db_session.commit()

    await delete_service.delete_user_data(db_session, user.id)
    await db_session.commit()

    result = await db_session.execute(
        select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_delete_retains_anonymized_audit(db_session: AsyncSession):
    """Audit trail retained but anonymized: PII scrubbed from detail, ip_address cleared."""
    user = await register_user(
        db_session, email="audit-del@example.com", password="Pass123!", ip_address="10.0.0.1"
    )
    await db_session.commit()

    await delete_service.delete_user_data(db_session, user.id)
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLogEvent).where(AuditLogEvent.user_id == user.id)
    )
    events = result.scalars().all()
    assert len(events) >= 2  # at least register + delete

    for event in events:
        assert event.ip_address is None  # IP scrubbed
        if event.detail:
            assert "email" not in event.detail  # email PII scrubbed


@pytest.mark.asyncio
async def test_delete_revokes_sessions(db_session: AsyncSession):
    """All sessions revoked after deletion."""
    user = await register_user(
        db_session, email="session-del@example.com", password="Pass123!"
    )
    await db_session.commit()

    _, token = await login_user(
        db_session, email="session-del@example.com", password="Pass123!"
    )
    await db_session.commit()

    await delete_service.delete_user_data(db_session, user.id)
    await db_session.commit()

    result = await db_session.execute(
        select(Session).where(Session.user_id == user.id)
    )
    sessions = result.scalars().all()
    for s in sessions:
        assert s.revoked is True


@pytest.mark.asyncio
async def test_delete_no_pii_recoverable(db_session: AsyncSession):
    """After deletion, no way to recover original email or password."""
    user = await register_user(
        db_session, email="recover@example.com", password="Pass123!"
    )
    await db_session.commit()
    user_id = user.id

    await delete_service.delete_user_data(db_session, user_id)
    await db_session.commit()

    # Check user table
    fetched = await db_session.execute(select(User).where(User.id == user_id))
    u = fetched.scalar_one()
    assert "recover@example.com" not in u.email

    # Check audit log for any remaining PII
    result = await db_session.execute(
        select(AuditLogEvent).where(AuditLogEvent.user_id == user_id)
    )
    events = result.scalars().all()
    for event in events:
        if event.detail:
            for value in event.detail.values():
                if isinstance(value, str):
                    assert "recover@example.com" not in value


@pytest.mark.asyncio
async def test_delete_nonexistent_user(db_session: AsyncSession):
    """Deleting nonexistent user returns False."""
    import uuid

    result = await delete_service.delete_user_data(db_session, uuid.uuid4())
    assert result is False
