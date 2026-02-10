import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CheatCodeRead(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    description: str
    category: str
    difficulty: str
    estimated_minutes: int
    steps: list[dict]
    potential_savings_min: Decimal | None = None
    potential_savings_max: Decimal | None = None

    model_config = {"from_attributes": True}


class RecommendationRead(BaseModel):
    id: uuid.UUID
    cheat_code: CheatCodeRead
    rank: int
    explanation: str
    confidence: str
    is_quick_win: bool

    model_config = {"from_attributes": True}


class StepRunRead(BaseModel):
    step_number: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class RunRead(BaseModel):
    id: uuid.UUID
    cheat_code: CheatCodeRead
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_steps: int
    completed_steps: int
    steps: list[StepRunRead] = []

    model_config = {"from_attributes": True}


class StartRunRequest(BaseModel):
    recommendation_id: uuid.UUID


class CompleteStepRequest(BaseModel):
    step_number: int
    notes: str | None = None
