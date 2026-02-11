import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class TransactionType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("merchants.id"), nullable=True, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    raw_description: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2), nullable=False
    )  # Always positive; type indicates direction
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    posted_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, native_enum=False), nullable=False
    )
    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
