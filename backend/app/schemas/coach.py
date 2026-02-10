from pydantic import BaseModel, Field


class CoachRequest(BaseModel):
    mode: str = Field(..., description="explain or execute")
    context_type: str = Field(..., description="Type of entity being discussed")
    context_id: str = Field(..., description="ID of the entity")
    question: str | None = None


class CoachResponse(BaseModel):
    mode: str
    response: str
    template_used: str
    inputs: dict
    caveats: list[str] = []
