import uuid
from datetime import datetime

from pydantic import BaseModel


class OnboardingStateRead(BaseModel):
    current_step: str
    consent_completed_at: datetime | None = None
    account_completed_at: datetime | None = None
    goals_completed_at: datetime | None = None
    top_3_completed_at: datetime | None = None
    first_win_completed_at: datetime | None = None

    model_config = {"from_attributes": True}
