"""Practice models: scenario definitions and user simulation runs.

Scenarios are interactive simulations with sliders.
ScenarioRun captures user's slider inputs, computed outcomes,
After-Action Review, and plan bridge status.

Practice outputs are CAPPED at medium confidence and cannot
enter Top 3 without real-data corroboration.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, generate_uuid


class ScenarioCategory(str, enum.Enum):
    save_money = "save_money"
    reduce_spending = "reduce_spending"
    pay_off_debt = "pay_off_debt"
    build_emergency_fund = "build_emergency_fund"
    budget_better = "budget_better"


class ScenarioRunStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class ScenarioDefinition(Base):
    """A practice scenario template with simulator sliders.

    sliders format: [{"key": "monthly_savings", "label": "Monthly Savings ($)",
                      "min": 0, "max": 1000, "step": 50, "default": 200}]

    initial_state format: {"balance": 5000, "monthly_income": 4000,
                           "monthly_expenses": 3500, "debt": 10000, ...}

    outcome_template: template string for rendering computed outcomes
    """

    __tablename__ = "scenario_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[ScenarioCategory] = mapped_column(
        Enum(ScenarioCategory, native_enum=False), nullable=False
    )
    initial_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    sliders: Mapped[dict] = mapped_column(JSON, nullable=False)
    outcome_template: Mapped[str] = mapped_column(String(2000), nullable=False)
    learning_points: Mapped[dict] = mapped_column(JSON, nullable=False)
    # learning_points: ["key takeaway 1", "key takeaway 2", ...]
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class ScenarioRun(TimestampMixin, Base):
    """User's practice simulation run.

    confidence is always capped at "medium" per PRD.
    plan_generated tracks whether user used "Turn into plan" bridge.
    """

    __tablename__ = "scenario_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenario_definitions.id"), nullable=False, index=True
    )
    slider_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # computed_outcome: {"projected_savings": 2400, "months_to_goal": 8, ...}
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium"
    )
    # confidence is ALWAYS "medium" — capped per PRD
    after_action_review: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # AAR: {"summary": "...", "what_worked": "...", "improvement": "...", "learning_points": [...]}
    status: Mapped[ScenarioRunStatus] = mapped_column(
        Enum(ScenarioRunStatus, native_enum=False),
        default=ScenarioRunStatus.in_progress,
        nullable=False,
    )
    plan_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
