import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class GoalType(str, enum.Enum):
    save_money = "save_money"
    reduce_spending = "reduce_spending"
    pay_off_debt = "pay_off_debt"
    build_emergency_fund = "build_emergency_fund"
    build_buffer = "build_buffer"
    budget_better = "budget_better"
    other = "other"


class GoalPriority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Goal(TimestampMixin, Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    goal_type: Mapped[GoalType] = mapped_column(
        Enum(GoalType, native_enum=False), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    target_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False, default=Decimal("0.00")
    )
    priority: Mapped[GoalPriority] = mapped_column(
        Enum(GoalPriority, native_enum=False),
        default=GoalPriority.medium,
        nullable=False,
    )
    target_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserConstraint(TimestampMixin, Base):
    """User-specified financial constraints (e.g. income, fixed expenses)."""

    __tablename__ = "user_constraints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    constraint_type: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
