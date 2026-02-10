"""Forecast schemas: request/response models for forecast API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DailyBalanceRead(BaseModel):
    day: int
    date: str
    projected: Decimal
    low: Decimal
    high: Decimal


class ForecastRead(BaseModel):
    id: uuid.UUID
    safe_to_spend_today: Decimal
    safe_to_spend_week: Decimal
    daily_balances: list[dict]
    projected_end_balance: Decimal
    projected_end_low: Decimal
    projected_end_high: Decimal
    confidence: str
    confidence_inputs: dict
    assumptions: list[str]
    urgency_score: int
    urgency_factors: dict
    computed_at: datetime

    model_config = {"from_attributes": True}


class ForecastSummaryRead(BaseModel):
    """Lightweight forecast summary for dashboard."""
    safe_to_spend_today: Decimal
    safe_to_spend_week: Decimal
    projected_end_balance: Decimal
    confidence: str
    urgency_score: int
    computed_at: datetime

    model_config = {"from_attributes": True}
