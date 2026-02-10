import uuid

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)
    parent_id: uuid.UUID | None = None
    icon: str | None = None


class CategoryRead(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None = None
    is_system: bool
    icon: str | None = None

    model_config = {"from_attributes": True}
