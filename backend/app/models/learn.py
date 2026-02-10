"""Learn models: lesson definitions and user progress tracking.

Lessons are static educational content with sections.
LessonProgress tracks each user's advancement through a lesson.
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


class LessonCategory(str, enum.Enum):
    save_money = "save_money"
    reduce_spending = "reduce_spending"
    pay_off_debt = "pay_off_debt"
    build_emergency_fund = "build_emergency_fund"
    budget_better = "budget_better"


class LessonStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


class LessonDefinition(Base):
    """A lesson template: educational content with sections.

    Sections format: [{"section_number": 1, "title": "...", "content": "...", "key_takeaway": "..."}]
    """

    __tablename__ = "lesson_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[LessonCategory] = mapped_column(
        Enum(LessonCategory, native_enum=False), nullable=False
    )
    sections: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_sections: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class LessonProgress(TimestampMixin, Base):
    """User's progress through a lesson."""

    __tablename__ = "lesson_progress"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lesson_definitions.id"), nullable=False, index=True
    )
    status: Mapped[LessonStatus] = mapped_column(
        Enum(LessonStatus, native_enum=False),
        default=LessonStatus.not_started,
        nullable=False,
    )
    completed_sections: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
