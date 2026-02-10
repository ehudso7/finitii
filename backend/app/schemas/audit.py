import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogEventRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    entity_type: str
    entity_id: uuid.UUID
    action: str
    detail: dict | None = None
    timestamp: datetime
    ip_address: str | None = None

    model_config = {"from_attributes": True}
