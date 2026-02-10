import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    account_type: str = Field(..., description="checking, savings, credit_card, loan, other")
    institution_name: str = Field(..., max_length=255)
    account_name: str = Field(..., max_length=255)
    current_balance: Decimal = Field(default=Decimal("0.00"))
    available_balance: Decimal | None = None
    currency: str = Field(default="USD", max_length=3)


class AccountBalanceUpdate(BaseModel):
    current_balance: Decimal
    available_balance: Decimal | None = None


class AccountRead(BaseModel):
    id: uuid.UUID
    account_type: str
    institution_name: str
    account_name: str
    current_balance: Decimal
    available_balance: Decimal | None = None
    currency: str
    is_manual: bool
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
