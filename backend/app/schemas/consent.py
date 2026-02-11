import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConsentGrant(BaseModel):
    consent_type: str = Field(..., description="One of: data_access, ai_memory, terms_of_service")


class ConsentRevoke(BaseModel):
    consent_type: str = Field(..., description="One of: data_access, ai_memory, terms_of_service")


class ConsentStatus(BaseModel):
    consent_type: str
    granted: bool
    granted_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConsentRecordRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    consent_type: str
    granted: bool
    granted_at: datetime
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    model_config = {"from_attributes": True}
