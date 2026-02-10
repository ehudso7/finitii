from uuid import UUID

from pydantic import BaseModel, Field


class CoachRequest(BaseModel):
    mode: str = Field(..., description="explain, execute, plan, review, or recap")
    context_type: str | None = Field(
        None, description="Type of entity being discussed (required for explain/execute)"
    )
    context_id: str | None = Field(
        None, description="ID of the entity (required for explain/execute)"
    )
    question: str | None = None


class CoachResponse(BaseModel):
    mode: str
    response: str
    template_used: str
    inputs: dict
    caveats: list[str] = []
    steps: list[dict] | None = None  # Phase 6: plan mode returns steps
    wins: list[dict] | None = None   # Phase 6: review mode returns wins


class CoachMemoryRead(BaseModel):
    id: UUID
    user_id: UUID
    tone: str
    aggressiveness: str

    model_config = {"from_attributes": True}


class CoachMemoryUpdate(BaseModel):
    tone: str | None = Field(
        None, description="Coach tone: encouraging, direct, or neutral"
    )
    aggressiveness: str | None = Field(
        None, description="Coach aggressiveness: conservative, moderate, or aggressive"
    )
