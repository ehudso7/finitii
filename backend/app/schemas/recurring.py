import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class RecurringPatternRead(BaseModel):
    id: uuid.UUID
    merchant_name: str | None = None
    category_name: str | None = None
    estimated_amount: Decimal
    amount_variance: Decimal
    frequency: str
    confidence: str
    confidence_inputs: dict
    next_expected_date: datetime | None = None
    last_observed_date: datetime | None = None
    is_active: bool

    model_config = {"from_attributes": True}
