"""CoachMemory model: stores coach personalization preferences.

Coach memory is limited to: tone, aggressiveness.
Goals and constraints are stored in separate models and referenced at query time.
Requires ai_memory consent — without it, coach uses defaults.
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class CoachTone(str, enum.Enum):
    encouraging = "encouraging"
    direct = "direct"
    neutral = "neutral"


class CoachAggressiveness(str, enum.Enum):
    conservative = "conservative"
    moderate = "moderate"
    aggressive = "aggressive"


class CoachMemory(TimestampMixin, Base):
    """User's coach personalization preferences.

    Requires ai_memory consent to read/write.
    One row per user (upsert pattern).
    """

    __tablename__ = "coach_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    tone: Mapped[CoachTone] = mapped_column(
        Enum(CoachTone, native_enum=False),
        nullable=False,
        default=CoachTone.neutral,
    )
    aggressiveness: Mapped[CoachAggressiveness] = mapped_column(
        Enum(CoachAggressiveness, native_enum=False),
        nullable=False,
        default=CoachAggressiveness.moderate,
    )
