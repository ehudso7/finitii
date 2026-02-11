from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VaultItemRead(BaseModel):
    id: UUID
    user_id: UUID
    transaction_id: UUID | None = None
    filename: str
    content_type: str
    file_size: int
    item_type: str
    description: str | None = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class LinkTransactionRequest(BaseModel):
    transaction_id: str
