import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus


@pytest.mark.asyncio
async def test_create_and_read_user(db_session: AsyncSession):
    """Round-trip: create user -> read user -> fields match."""
    user = User(email="test@example.com", password_hash="fakehash123")
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    fetched = result.scalar_one()

    assert fetched.id is not None
    assert fetched.email == "test@example.com"
    assert fetched.password_hash == "fakehash123"
    assert fetched.status == UserStatus.active
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.deleted_at is None


@pytest.mark.asyncio
async def test_user_status_default_active(db_session: AsyncSession):
    """User status defaults to active."""
    user = User(email="active@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.email == "active@example.com"))
    fetched = result.scalar_one()
    assert fetched.status == UserStatus.active


@pytest.mark.asyncio
async def test_user_unique_email(db_session: AsyncSession):
    """Duplicate email raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    user1 = User(email="dup@example.com", password_hash="hash1")
    db_session.add(user1)
    await db_session.commit()

    user2 = User(email="dup@example.com", password_hash="hash2")
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_user_uuid_generated(db_session: AsyncSession):
    """User id is a UUID generated automatically."""
    import uuid

    user = User(email="uuid@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.email == "uuid@example.com"))
    fetched = result.scalar_one()
    assert isinstance(fetched.id, uuid.UUID)
