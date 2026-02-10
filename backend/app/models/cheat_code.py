import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, generate_uuid


class CheatCodeDifficulty(str, enum.Enum):
    quick_win = "quick_win"  # ≤10 min
    easy = "easy"           # ≤30 min
    medium = "medium"       # ≤2 hours
    involved = "involved"   # longer


class CheatCodeCategory(str, enum.Enum):
    save_money = "save_money"
    reduce_spending = "reduce_spending"
    pay_off_debt = "pay_off_debt"
    build_emergency_fund = "build_emergency_fund"
    budget_better = "budget_better"


class RunStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    paused = "paused"
    completed = "completed"
    abandoned = "abandoned"
    archived = "archived"


class OutcomeType(str, enum.Enum):
    user_reported = "user_reported"
    inferred = "inferred"


class VerificationStatus(str, enum.Enum):
    unverified = "unverified"
    verified = "verified"
    disputed = "disputed"


class CheatCodeDefinition(Base):
    """A cheat code template: the "what to do" and "how to do it"."""

    __tablename__ = "cheat_code_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[CheatCodeCategory] = mapped_column(
        Enum(CheatCodeCategory, native_enum=False), nullable=False
    )
    difficulty: Mapped[CheatCodeDifficulty] = mapped_column(
        Enum(CheatCodeDifficulty, native_enum=False), nullable=False
    )
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[dict] = mapped_column(JSON, nullable=False)
    # steps format: [{"step_number": 1, "title": "...", "description": "...", "estimated_minutes": 5}]
    potential_savings_min: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    potential_savings_max: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class Recommendation(Base):
    """A recommended cheat code for a user, with ranking and explanation."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    cheat_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cheat_code_definitions.id"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)
    explanation_template: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation_inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    is_quick_win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class CheatCodeRun(TimestampMixin, Base):
    """A user's run of a cheat code."""

    __tablename__ = "cheat_code_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    cheat_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cheat_code_definitions.id"), nullable=False
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False),
        default=RunStatus.not_started,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class StepRun(Base):
    """A single step execution within a cheat code run."""

    __tablename__ = "step_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cheat_code_runs.id"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False),
        default=RunStatus.not_started,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class CheatCodeOutcome(TimestampMixin, Base):
    """Outcome of a completed cheat code run.

    Captures both user-reported and inferred savings/results.
    No automation of money movement — outcome is informational only.
    """

    __tablename__ = "cheat_code_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cheat_code_runs.id"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    outcome_type: Mapped[OutcomeType] = mapped_column(
        Enum(OutcomeType, native_enum=False), nullable=False
    )
    reported_savings: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    reported_savings_period: Mapped[str | None] = mapped_column(
        String(50), nullable=True  # "monthly", "one_time", "annual"
    )
    inferred_savings: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    inferred_method: Mapped[str | None] = mapped_column(
        String(255), nullable=True  # e.g. "recurring_pattern_removed"
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False),
        default=VerificationStatus.unverified,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    user_satisfaction: Mapped[int | None] = mapped_column(
        Integer, nullable=True  # 1-5 rating
    )
