import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentRecord, ConsentType
from app.models.user import User


async def _create_user(db_session: AsyncSession, email: str = "test@example.com") -> User:
    user = User(email=email, password_hash="fakehash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_consent_record(db_session: AsyncSession):
    """Create consent record and verify fields."""
    user = await _create_user(db_session)

    consent = ConsentRecord(
        user_id=user.id,
        consent_type=ConsentType.data_access,
        granted=True,
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0",
    )
    db_session.add(consent)
    await db_session.commit()

    result = await db_session.execute(
        select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    )
    fetched = result.scalar_one()

    assert fetched.id is not None
    assert fetched.user_id == user.id
    assert fetched.consent_type == ConsentType.data_access
    assert fetched.granted is True
    assert fetched.granted_at is not None
    assert fetched.revoked_at is None
    assert fetched.ip_address == "127.0.0.1"
    assert fetched.user_agent == "TestAgent/1.0"


@pytest.mark.asyncio
async def test_ai_memory_default_not_granted(db_session: AsyncSession):
    """AI memory consent defaults to not granted (granted=False)."""
    user = await _create_user(db_session)

    consent = ConsentRecord(
        user_id=user.id,
        consent_type=ConsentType.ai_memory,
        granted=False,
    )
    db_session.add(consent)
    await db_session.commit()

    result = await db_session.execute(
        select(ConsentRecord).where(
            ConsentRecord.user_id == user.id,
            ConsentRecord.consent_type == ConsentType.ai_memory,
        )
    )
    fetched = result.scalar_one()
    assert fetched.granted is False


@pytest.mark.asyncio
async def test_consent_fk_to_user(db_session: AsyncSession):
    """FK constraint to user is enforced."""
    import uuid

    from sqlalchemy.exc import IntegrityError

    consent = ConsentRecord(
        user_id=uuid.uuid4(),  # non-existent user
        consent_type=ConsentType.data_access,
        granted=True,
    )
    db_session.add(consent)
    with pytest.raises(IntegrityError):
        await db_session.commit()
