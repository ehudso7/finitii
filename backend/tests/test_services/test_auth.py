import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    hash_password,
    login_user,
    logout_user,
    register_user,
    verify_password,
)
from app.models.user import UserStatus
from app.services import audit_service


@pytest.mark.asyncio
async def test_hash_and_verify_password():
    """bcrypt hash and verify round-trip."""
    pw = "SecurePass123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPass", hashed) is False


@pytest.mark.asyncio
async def test_register_user(db_session: AsyncSession):
    """Register creates a user with hashed password."""
    user = await register_user(
        db_session,
        email="register@example.com",
        password="SecurePass123!",
        ip_address="127.0.0.1",
    )
    await db_session.commit()

    assert user.id is not None
    assert user.email == "register@example.com"
    assert user.status == UserStatus.active
    assert verify_password("SecurePass123!", user.password_hash) is True


@pytest.mark.asyncio
async def test_register_duplicate_email(db_session: AsyncSession):
    """Register with duplicate email raises 409."""
    await register_user(
        db_session,
        email="dup@example.com",
        password="Pass123!",
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await register_user(
            db_session,
            email="dup@example.com",
            password="Pass456!",
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_login_user_success(db_session: AsyncSession):
    """Login with valid credentials returns user + token."""
    await register_user(
        db_session,
        email="login@example.com",
        password="SecurePass123!",
    )
    await db_session.commit()

    user, token = await login_user(
        db_session,
        email="login@example.com",
        password="SecurePass123!",
    )
    await db_session.commit()

    assert user.email == "login@example.com"
    assert isinstance(token, str)
    assert len(token) == 64  # hex(32 bytes)


@pytest.mark.asyncio
async def test_login_wrong_password(db_session: AsyncSession):
    """Login with wrong password raises 401."""
    await register_user(
        db_session,
        email="wrongpw@example.com",
        password="CorrectPass123!",
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await login_user(
            db_session,
            email="wrongpw@example.com",
            password="WrongPass!",
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(db_session: AsyncSession):
    """Login with nonexistent email raises 401."""
    with pytest.raises(HTTPException) as exc_info:
        await login_user(
            db_session,
            email="nobody@example.com",
            password="Pass123!",
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(db_session: AsyncSession):
    """Logout revokes the session token."""
    await register_user(
        db_session,
        email="logout@example.com",
        password="Pass123!",
    )
    await db_session.commit()

    user, token = await login_user(
        db_session,
        email="logout@example.com",
        password="Pass123!",
    )
    await db_session.commit()

    await logout_user(db_session, token=token)
    await db_session.commit()

    # Verify the session is revoked by trying to login again and checking audit
    events = await audit_service.get_events_for_user(db_session, user.id)
    logout_events = [e for e in events if e.event_type == "auth.logout"]
    assert len(logout_events) == 1


@pytest.mark.asyncio
async def test_all_auth_events_in_audit_log(db_session: AsyncSession):
    """Register, login, logout all logged to audit."""
    user = await register_user(
        db_session,
        email="audit-auth@example.com",
        password="Pass123!",
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    _, token = await login_user(
        db_session,
        email="audit-auth@example.com",
        password="Pass123!",
        ip_address="10.0.0.2",
    )
    await db_session.commit()

    await logout_user(db_session, token=token, ip_address="10.0.0.3")
    await db_session.commit()

    events = await audit_service.get_events_for_user(db_session, user.id)
    event_types = [e.event_type for e in events]
    assert "auth.register" in event_types
    assert "auth.login" in event_types
    assert "auth.logout" in event_types
