# Import all models so Base.metadata is populated for Alembic autogenerate.
from app.models.user import User  # noqa: F401
from app.models.consent import ConsentRecord  # noqa: F401
from app.models.audit import AuditLogEvent  # noqa: F401
from app.models.session import Session  # noqa: F401
