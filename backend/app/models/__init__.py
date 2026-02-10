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
