"""Phase 6 service tests: coach memory service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_memory import CoachAggressiveness, CoachMemory, CoachTone
from app.models.consent import ConsentRecord, ConsentType
from app.models.user import User
from app.services import coach_memory_service


async def _create_user(db: AsyncSession, email: str = "cm@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _grant_ai_memory(db: AsyncSession, user_id) -> None:
    consent = ConsentRecord(
        user_id=user_id,
        consent_type=ConsentType.ai_memory,
        granted=True,
    )
    db.add(consent)
    await db.flush()


# --- get_memory ---

@pytest.mark.asyncio
async def test_get_memory_no_consent(db_session: AsyncSession):
    """Returns None when ai_memory consent not granted."""
    user = await _create_user(db_session)
    result = await coach_memory_service.get_memory(db_session, user_id=user.id)
    assert result is None


@pytest.mark.asyncio
async def test_get_memory_with_consent_no_record(db_session: AsyncSession):
    """Returns None when consent granted but no memory stored."""
    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)
    result = await coach_memory_service.get_memory(db_session, user_id=user.id)
    assert result is None


@pytest.mark.asyncio
async def test_get_memory_with_consent_and_record(db_session: AsyncSession):
    """Returns memory when consent granted and memory exists."""
    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)
    await coach_memory_service.set_memory(
        db_session, user_id=user.id, tone=CoachTone.direct
    )
    result = await coach_memory_service.get_memory(db_session, user_id=user.id)
    assert result is not None
    assert result.tone == CoachTone.direct


# --- set_memory ---

@pytest.mark.asyncio
async def test_set_memory_no_consent_raises(db_session: AsyncSession):
    """Raises ValueError when ai_memory consent not granted."""
    user = await _create_user(db_session)
    with pytest.raises(ValueError, match="ai_memory consent required"):
        await coach_memory_service.set_memory(
            db_session, user_id=user.id, tone=CoachTone.encouraging
        )


@pytest.mark.asyncio
async def test_set_memory_create(db_session: AsyncSession):
    """Creates new memory record with consent."""
    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)

    memory = await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        tone=CoachTone.encouraging,
        aggressiveness=CoachAggressiveness.aggressive,
    )
    assert memory.tone == CoachTone.encouraging
    assert memory.aggressiveness == CoachAggressiveness.aggressive
    assert memory.user_id == user.id


@pytest.mark.asyncio
async def test_set_memory_update(db_session: AsyncSession):
    """Updates existing memory record."""
    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)

    # Create
    await coach_memory_service.set_memory(
        db_session, user_id=user.id, tone=CoachTone.neutral
    )
    # Update
    memory = await coach_memory_service.set_memory(
        db_session, user_id=user.id, tone=CoachTone.direct
    )
    assert memory.tone == CoachTone.direct


@pytest.mark.asyncio
async def test_set_memory_partial_update(db_session: AsyncSession):
    """Partial update only changes specified fields."""
    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)

    await coach_memory_service.set_memory(
        db_session,
        user_id=user.id,
        tone=CoachTone.encouraging,
        aggressiveness=CoachAggressiveness.conservative,
    )
    # Update only aggressiveness
    memory = await coach_memory_service.set_memory(
        db_session, user_id=user.id, aggressiveness=CoachAggressiveness.aggressive
    )
    assert memory.tone == CoachTone.encouraging  # unchanged
    assert memory.aggressiveness == CoachAggressiveness.aggressive


@pytest.mark.asyncio
async def test_set_memory_audit_logged(db_session: AsyncSession):
    """Coach memory changes are audit-logged."""
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)

    await coach_memory_service.set_memory(
        db_session, user_id=user.id, tone=CoachTone.direct
    )

    from sqlalchemy import select
    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "coach_memory.create",
        )
    )
    event = result.scalar_one()
    assert event.detail["tone"] == "direct"


# --- delete_memory ---

@pytest.mark.asyncio
async def test_delete_memory_exists(db_session: AsyncSession):
    """Delete returns True when memory exists."""
    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)
    await coach_memory_service.set_memory(
        db_session, user_id=user.id, tone=CoachTone.direct
    )

    deleted = await coach_memory_service.delete_memory(
        db_session, user_id=user.id
    )
    assert deleted is True

    # Verify gone
    result = await coach_memory_service.get_memory(db_session, user_id=user.id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_memory_not_exists(db_session: AsyncSession):
    """Delete returns False when no memory exists."""
    user = await _create_user(db_session)
    deleted = await coach_memory_service.delete_memory(
        db_session, user_id=user.id
    )
    assert deleted is False


@pytest.mark.asyncio
async def test_delete_memory_audit_logged(db_session: AsyncSession):
    """Coach memory deletion is audit-logged."""
    from app.models.audit import AuditLogEvent
    from sqlalchemy import select

    user = await _create_user(db_session)
    await _grant_ai_memory(db_session, user.id)
    await coach_memory_service.set_memory(
        db_session, user_id=user.id, tone=CoachTone.neutral
    )
    await coach_memory_service.delete_memory(db_session, user_id=user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "coach_memory.deleted",
        )
    )
    event = result.scalar_one()
    assert event is not None
