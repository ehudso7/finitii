import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentType
from app.models.user import User
from app.services import audit_service, consent_service


async def _create_user(db_session: AsyncSession) -> User:
    user = User(email="consent-svc@example.com", password_hash="fakehash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_grant_consent(db_session: AsyncSession):
    """Grant data_access -> check returns True."""
    user = await _create_user(db_session)

    consent = await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )
    await db_session.commit()

    assert consent.granted is True
    assert consent.revoked_at is None

    is_granted = await consent_service.check_consent(
        db_session, user.id, ConsentType.data_access
    )
    assert is_granted is True


@pytest.mark.asyncio
async def test_revoke_consent(db_session: AsyncSession):
    """Grant -> revoke -> check returns False."""
    user = await _create_user(db_session)

    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await db_session.commit()

    revoked = await consent_service.revoke_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await db_session.commit()

    assert revoked is not None
    assert revoked.granted is False
    assert revoked.revoked_at is not None

    is_granted = await consent_service.check_consent(
        db_session, user.id, ConsentType.data_access
    )
    assert is_granted is False


@pytest.mark.asyncio
async def test_ai_memory_never_auto_granted(db_session: AsyncSession):
    """AI memory consent is never auto-granted; defaults OFF."""
    user = await _create_user(db_session)

    # Without explicitly granting, check returns False
    is_granted = await consent_service.check_consent(
        db_session, user.id, ConsentType.ai_memory
    )
    assert is_granted is False


@pytest.mark.asyncio
async def test_ai_memory_explicit_grant(db_session: AsyncSession):
    """AI memory can be explicitly granted."""
    user = await _create_user(db_session)

    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.ai_memory,
    )
    await db_session.commit()

    is_granted = await consent_service.check_consent(
        db_session, user.id, ConsentType.ai_memory
    )
    assert is_granted is True


@pytest.mark.asyncio
async def test_all_consent_actions_in_audit_log(db_session: AsyncSession):
    """Grant + revoke both appear in audit log."""
    user = await _create_user(db_session)

    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    await consent_service.revoke_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
        ip_address="10.0.0.2",
    )
    await db_session.commit()

    events = await audit_service.get_events_for_user(db_session, user.id)
    consent_events = [e for e in events if e.entity_type == "ConsentRecord"]
    assert len(consent_events) == 2
    assert consent_events[0].event_type == "consent.granted"
    assert consent_events[1].event_type == "consent.revoked"


@pytest.mark.asyncio
async def test_get_all_consents(db_session: AsyncSession):
    """get_all_consents returns all records including revoked."""
    user = await _create_user(db_session)

    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.terms_of_service,
    )
    await db_session.commit()

    await consent_service.revoke_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await db_session.commit()

    all_consents = await consent_service.get_all_consents(db_session, user.id)
    assert len(all_consents) == 2


@pytest.mark.asyncio
async def test_duplicate_grant_returns_existing(db_session: AsyncSession):
    """Granting same consent twice returns the existing record, not a duplicate."""
    user = await _create_user(db_session)

    c1 = await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await db_session.commit()

    c2 = await consent_service.grant_consent(
        db_session,
        user_id=user.id,
        consent_type=ConsentType.data_access,
    )
    await db_session.commit()

    assert c1.id == c2.id

    all_consents = await consent_service.get_all_consents(db_session, user.id)
    data_access = [c for c in all_consents if c.consent_type == ConsentType.data_access]
    assert len(data_access) == 1
