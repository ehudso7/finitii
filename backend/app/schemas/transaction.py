import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    raw_description: str = Field(..., max_length=500)
    amount: Decimal = Field(..., gt=0)
    transaction_type: str = Field(..., description="debit or credit")
    transaction_date: datetime
    posted_date: datetime | None = None
    is_pending: bool = False
    currency: str = Field(default="USD", max_length=3)
    category_id: uuid.UUID | None = None


class TransactionRecategorize(BaseModel):
    category_id: uuid.UUID


class TransactionRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    merchant_name: str | None = None
    category_name: str | None = None
    raw_description: str
    normalized_description: str
    amount: Decimal
    currency: str
    transaction_date: datetime
    posted_date: datetime | None = None
    is_pending: bool
    transaction_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
