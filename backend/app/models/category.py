import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )  # null = system default
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)


# System categories to seed
SYSTEM_CATEGORIES = [
    {"name": "Groceries", "icon": "cart"},
    {"name": "Dining", "icon": "utensils"},
    {"name": "Transport", "icon": "car"},
    {"name": "Utilities", "icon": "bolt"},
    {"name": "Entertainment", "icon": "film"},
    {"name": "Healthcare", "icon": "heart"},
    {"name": "Shopping", "icon": "bag"},
    {"name": "Income", "icon": "dollar"},
    {"name": "Transfers", "icon": "arrows"},
    {"name": "Other", "icon": "ellipsis"},
]
