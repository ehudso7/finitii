from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LessonRead(BaseModel):
    id: UUID
    code: str
    title: str
    description: str
    category: str
    sections: list[dict]
    total_sections: int
    estimated_minutes: int
    display_order: int

    model_config = {"from_attributes": True}


class LessonProgressRead(BaseModel):
    id: UUID
    user_id: UUID
    lesson_id: UUID
    status: str
    completed_sections: int
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class StartLessonRequest(BaseModel):
    lesson_id: str


class CompleteSectionRequest(BaseModel):
    lesson_id: str
    section_number: int
