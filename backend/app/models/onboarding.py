import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class OnboardingStep(str, enum.Enum):
    consent = "consent"
    account_link = "account_link"
    goals = "goals"
    top_3 = "top_3"
    first_win = "first_win"
    completed = "completed"


class OnboardingState(Base):
    """Tracks user progress through onboarding gates.

    Gate order: consent → account_link → goals → top_3 → first_win → completed.
    Cannot skip steps. first_win requires starting + completing 1 cheat code step.
    """

    __tablename__ = "onboarding_states"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    current_step: Mapped[OnboardingStep] = mapped_column(
        Enum(OnboardingStep, native_enum=False),
        default=OnboardingStep.consent,
        nullable=False,
    )
    consent_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    account_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    goals_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    top_3_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_win_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_win_cheat_code_run_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )
