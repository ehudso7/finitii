"""Authentication: register, login, logout, get_current_user.

MVP session-based auth with bcrypt password hashing.
All auth events logged to audit.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.session import Session
from app.models.user import User, UserStatus
from app.services import audit_service

SESSION_DURATION_HOURS = 24
SESSION_TOKEN_HEADER = "X-Session-Token"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _generate_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_hex(32)


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> User:
    """Register a new user. Raises HTTPException if email taken."""
    # Check for existing user
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email,
        password_hash=hash_password(password),
        status=UserStatus.active,
    )
    db.add(user)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user.id,
        event_type="auth.register",
        entity_type="User",
        entity_id=user.id,
        action="register",
        detail={"email": email},
        ip_address=ip_address,
    )

    return user


async def login_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> tuple[User, str]:
    """Authenticate user, create session, return (user, token).

    Raises HTTPException on invalid credentials or inactive account.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    token = _generate_token()
    session = Session(
        user_id=user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS),
    )
    db.add(session)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user.id,
        event_type="auth.login",
        entity_type="Session",
        entity_id=session.id,
        action="login",
        ip_address=ip_address,
    )

    return user, token


async def logout_user(
    db: AsyncSession,
    *,
    token: str,
    ip_address: str | None = None,
) -> None:
    """Revoke a session token."""
    result = await db.execute(select(Session).where(Session.token == token))
    session = result.scalar_one_or_none()
    if session is None:
        return

    session.revoked = True
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=session.user_id,
        event_type="auth.logout",
        entity_type="Session",
        entity_id=session.id,
        action="logout",
        ip_address=ip_address,
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: extract and validate the session token, return current user.

    Raises HTTPException 401 if token is missing, invalid, expired, or revoked.
    """
    token = request.headers.get(SESSION_TOKEN_HEADER)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    result = await db.execute(select(Session).where(Session.token == token))
    session = result.scalar_one_or_none()

    if session is None or session.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked session",
        )

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user
