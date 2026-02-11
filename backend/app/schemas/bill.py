"""Bill schemas: request/response models for bills API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class BillRead(BaseModel):
    """A bill/subscription — derived view over RecurringPattern."""
    id: uuid.UUID
    label: str | None = None
    estimated_amount: Decimal
    frequency: str
    confidence: str
    next_expected_date: datetime | None = None
    last_observed_date: datetime | None = None
    is_essential: bool
    is_manual: bool
    is_active: bool
    merchant_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class CreateManualBillRequest(BaseModel):
    label: str
    estimated_amount: Decimal
    frequency: str
    next_expected_date: datetime
    is_essential: bool = False
    category_id: uuid.UUID | None = None


class UpdateBillRequest(BaseModel):
    label: str | None = None
    estimated_amount: Decimal | None = None
    frequency: str | None = None
    next_expected_date: datetime | None = None
    is_essential: bool | None = None


class ToggleEssentialRequest(BaseModel):
    is_essential: bool


class BillSummaryRead(BaseModel):
    total_bills: int
    total_monthly_estimate: Decimal
    by_confidence: dict
    essential_count: int
    manual_count: int
