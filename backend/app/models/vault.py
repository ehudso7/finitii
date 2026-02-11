"""Vault models: VaultItem for receipt/document storage.

Phase 8: Vault — receipts & documents lite.

VaultItem stores metadata for uploaded files.
Actual file bytes are handled by the storage abstraction (not in DB).
Deleting an account must delete all vault items and their files.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, Enum, ForeignKey, Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class VaultItemType(str, enum.Enum):
    receipt = "receipt"
    document = "document"


class VaultItem(TimestampMixin, Base):
    """A receipt or document stored in the vault.

    Actual file content is stored via the storage backend (local filesystem or S3).
    This model stores metadata + a storage_key for retrieval.
    """

    __tablename__ = "vault_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    item_type: Mapped[VaultItemType] = mapped_column(
        Enum(VaultItemType, native_enum=False),
        nullable=False,
        default=VaultItemType.receipt,
    )
    storage_key: Mapped[str] = mapped_column(
        String(1000), unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
