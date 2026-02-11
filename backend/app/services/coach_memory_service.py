"""Coach memory service: CRUD for coach personalization preferences.

Requires ai_memory consent. Without consent, returns None (coach uses defaults).
All writes audit-logged.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_memory import CoachAggressiveness, CoachMemory, CoachTone
from app.models.consent import ConsentType
from app.services import audit_service, consent_service


async def get_memory(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> CoachMemory | None:
    """Get coach memory for a user. Returns None if no ai_memory consent."""
    has_consent = await consent_service.check_consent(
        db, user_id, ConsentType.ai_memory
    )
    if not has_consent:
        return None

    result = await db.execute(
        select(CoachMemory).where(CoachMemory.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def set_memory(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tone: CoachTone | None = None,
    aggressiveness: CoachAggressiveness | None = None,
    ip_address: str | None = None,
) -> CoachMemory:
    """Set coach memory preferences. Requires ai_memory consent.

    Raises ValueError if consent not granted.
    Uses upsert pattern: creates or updates existing record.
    """
    has_consent = await consent_service.check_consent(
        db, user_id, ConsentType.ai_memory
    )
    if not has_consent:
        raise ValueError(
            "ai_memory consent required to store coach preferences"
        )

    result = await db.execute(
        select(CoachMemory).where(CoachMemory.user_id == user_id)
    )
    memory = result.scalar_one_or_none()

    if memory is None:
        memory = CoachMemory(
            user_id=user_id,
            tone=tone or CoachTone.neutral,
            aggressiveness=aggressiveness or CoachAggressiveness.moderate,
        )
        db.add(memory)
        action = "create"
    else:
        if tone is not None:
            memory.tone = tone
        if aggressiveness is not None:
            memory.aggressiveness = aggressiveness
        action = "update"

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type=f"coach_memory.{action}",
        entity_type="CoachMemory",
        entity_id=memory.id,
        action=action,
        detail={
            "tone": memory.tone.value,
            "aggressiveness": memory.aggressiveness.value,
        },
        ip_address=ip_address,
    )

    return memory


async def delete_memory(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> bool:
    """Delete coach memory (e.g. when ai_memory consent revoked).

    Returns True if memory existed and was deleted.
    """
    result = await db.execute(
        select(CoachMemory).where(CoachMemory.user_id == user_id)
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        return False

    memory_id = memory.id
    await db.delete(memory)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="coach_memory.deleted",
        entity_type="CoachMemory",
        entity_id=memory_id,
        action="delete",
        ip_address=ip_address,
    )

    return True
