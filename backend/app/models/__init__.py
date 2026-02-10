# Import all models so Base.metadata is populated for Alembic autogenerate.
from app.models.user import User  # noqa: F401
from app.models.consent import ConsentRecord  # noqa: F401
from app.models.audit import AuditLogEvent  # noqa: F401
from app.models.session import Session  # noqa: F401
from app.models.connection import Connection  # noqa: F401
from app.models.account import Account  # noqa: F401
from app.models.merchant import Merchant  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.recurring import RecurringPattern  # noqa: F401
from app.models.onboarding import OnboardingState  # noqa: F401
from app.models.goal import Goal, UserConstraint  # noqa: F401
from app.models.cheat_code import (  # noqa: F401
    CheatCodeDefinition,
    CheatCodeOutcome,
    Recommendation,
    CheatCodeRun,
    StepRun,
)
from app.models.forecast import ForecastSnapshot  # noqa: F401
from app.models.coach_memory import CoachMemory  # noqa: F401
from app.models.learn import LessonDefinition, LessonProgress  # noqa: F401
from app.models.practice import ScenarioDefinition, ScenarioRun  # noqa: F401
from app.models.vault import VaultItem  # noqa: F401
