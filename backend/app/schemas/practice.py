from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ScenarioRead(BaseModel):
    id: UUID
    code: str
    title: str
    description: str
    category: str
    initial_state: dict
    sliders: list[dict]
    outcome_template: str
    learning_points: list[str]
    estimated_minutes: int
    display_order: int

    model_config = {"from_attributes": True}


class ScenarioRunRead(BaseModel):
    id: UUID
    user_id: UUID
    scenario_id: UUID
    slider_values: dict
    computed_outcome: dict | None = None
    confidence: str
    after_action_review: dict | None = None
    status: str
    plan_generated: bool
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class StartScenarioRequest(BaseModel):
    scenario_id: str


class SimulateRequest(BaseModel):
    run_id: str
    slider_values: dict


class CompleteScenarioRequest(BaseModel):
    run_id: str


class TurnIntoPlanRequest(BaseModel):
    run_id: str


class PracticePlanRead(BaseModel):
    source: str
    scenario_title: str
    confidence: str
    steps: list[dict]
    caveats: list[str]
