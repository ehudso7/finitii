import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
