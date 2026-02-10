import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class GoalCreate(BaseModel):
    goal_type: str
    title: str = Field(..., max_length=255)
    description: str | None = None
    target_amount: Decimal | None = None
    priority: str = "medium"
    target_date: datetime | None = None


class GoalRead(BaseModel):
    id: uuid.UUID
    goal_type: str
    title: str
    description: str | None = None
    target_amount: Decimal | None = None
    current_amount: Decimal
    priority: str
    target_date: datetime | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class ConstraintCreate(BaseModel):
    constraint_type: str = Field(..., max_length=100)
    label: str = Field(..., max_length=255)
    amount: Decimal | None = None
    notes: str | None = None


class ConstraintRead(BaseModel):
    id: uuid.UUID
    constraint_type: str
    label: str
    amount: Decimal | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}
