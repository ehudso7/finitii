import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class Frequency(str, enum.Enum):
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class Confidence(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RecurringPattern(TimestampMixin, Base):
    __tablename__ = "recurring_patterns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("merchants.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    estimated_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )
    amount_variance: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False, default=Decimal("0.00")
    )
    frequency: Mapped[Frequency] = mapped_column(
        Enum(Frequency, native_enum=False), nullable=False
    )
    confidence: Mapped[Confidence] = mapped_column(
        Enum(Confidence, native_enum=False), nullable=False
    )
    next_expected_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_observed_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
