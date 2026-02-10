"""Forecast models: snapshots, confidence, and assumptions.

A ForecastSnapshot stores a point-in-time forecast computation with:
- Safe-to-Spend (today + week)
- 30-day daily balance projections with volatility bands
- Explicit assumptions recorded for every forecast
- Confidence attached to all outputs
"""

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, generate_uuid


class ForecastConfidence(str, enum.Enum):
    """Confidence in forecast accuracy.

    high: ≥3 months of data, ≥3 recurring patterns with high confidence
    medium: ≥1 month of data, ≥1 recurring pattern
    low: insufficient data or highly volatile spending
    """
    high = "high"
    medium = "medium"
    low = "low"


class ForecastSnapshot(TimestampMixin, Base):
    """A point-in-time forecast for a user.

    Every forecast records:
    - safe_to_spend_today / safe_to_spend_week: conservative available amounts
    - daily_balances: 30-day projection [{day, projected, low, high}]
    - assumptions: explicit list of what the forecast is based on
    - confidence + confidence_inputs: full explainability
    """

    __tablename__ = "forecast_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    # Safe-to-Spend
    safe_to_spend_today: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )
    safe_to_spend_week: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )

    # 30-day projection stored as JSON array
    # [{day: 1, date: "2026-02-11", projected: 1234.56, low: 1100.00, high: 1350.00}, ...]
    daily_balances: Mapped[dict] = mapped_column(JSON, nullable=False)

    # End-of-30-day summary
    projected_end_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )
    projected_end_low: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )
    projected_end_high: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )

    # Confidence
    confidence: Mapped[ForecastConfidence] = mapped_column(
        Enum(ForecastConfidence, native_enum=False), nullable=False
    )
    confidence_inputs: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Explicit assumptions
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    # e.g. ["Income of $X expected on date Y", "N recurring charges totaling $Z"]

    # Urgency score (0-100): higher = more urgent financial situation
    urgency_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urgency_factors: Mapped[dict] = mapped_column(JSON, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
