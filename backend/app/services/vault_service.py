"""Vault service: upload, list, get, link-to-transaction, delete.

Phase 8: Vault — receipts & documents lite.

Key rules:
- Storage is secure (no public access)
- All writes audit-logged
- delete_user_vault_items() hard-deletes DB rows + storage files (ship gate)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vault import VaultItem, VaultItemType
from app.services import audit_service
from app.services.storage import generate_storage_key, get_storage


# Max file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed content types
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}


async def upload(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    filename: str,
    content_type: str,
    data: bytes,
    item_type: str = "receipt",
    description: str | None = None,
    transaction_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> VaultItem:
    """Upload a file to the vault.

    Validates file size and content type.
    Stores file via storage backend and creates DB record.
    """
    if len(data) > MAX_FILE_SIZE:
        raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB.")

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(
            f"Unsupported file type: {content_type}. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    # Validate item_type
    try:
        vault_type = VaultItemType(item_type)
    except ValueError:
        raise ValueError(
            f"Invalid item_type: {item_type}. "
            f"Must be one of: {', '.join(t.value for t in VaultItemType)}"
        )

    # Generate storage key and save file
    storage_key = generate_storage_key(user_id, filename)
    storage = get_storage()
    await storage.save(storage_key, data, content_type)

    # Create DB record
    item = VaultItem(
        user_id=user_id,
        transaction_id=transaction_id,
        filename=filename,
        content_type=content_type,
        file_size=len(data),
        item_type=vault_type,
        storage_key=storage_key,
        description=description,
    )
    db.add(item)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="vault.uploaded",
        entity_type="VaultItem",
        entity_id=item.id,
        action="upload",
        detail={
            "filename": filename,
            "content_type": content_type,
            "file_size": len(data),
            "item_type": vault_type.value,
        },
        ip_address=ip_address,
    )

    return item


async def list_items(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    item_type: str | None = None,
    transaction_id: uuid.UUID | None = None,
) -> list[VaultItem]:
    """List vault items for a user, optionally filtered."""
    stmt = (
        select(VaultItem)
        .where(VaultItem.user_id == user_id)
        .order_by(VaultItem.uploaded_at.desc())
    )
    if item_type:
        stmt = stmt.where(VaultItem.item_type == item_type)
    if transaction_id:
        stmt = stmt.where(VaultItem.transaction_id == transaction_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_item(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
) -> VaultItem:
    """Get a single vault item (user-scoped)."""
    result = await db.execute(
        select(VaultItem).where(
            VaultItem.id == item_id,
            VaultItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ValueError("Vault item not found.")
    return item


async def get_file_data(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[VaultItem, bytes]:
    """Get vault item metadata and file data for download."""
    item = await get_item(db, item_id=item_id, user_id=user_id)
    storage = get_storage()
    data = await storage.load(item.storage_key)
    return item, data


async def link_to_transaction(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    ip_address: str | None = None,
) -> VaultItem:
    """Link a vault item to a transaction."""
    item = await get_item(db, item_id=item_id, user_id=user_id)
    item.transaction_id = transaction_id
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="vault.linked",
        entity_type="VaultItem",
        entity_id=item.id,
        action="link_transaction",
        detail={"transaction_id": str(transaction_id)},
        ip_address=ip_address,
    )

    return item


async def unlink_transaction(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> VaultItem:
    """Unlink a vault item from its transaction."""
    item = await get_item(db, item_id=item_id, user_id=user_id)
    old_txn = item.transaction_id
    item.transaction_id = None
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="vault.unlinked",
        entity_type="VaultItem",
        entity_id=item.id,
        action="unlink_transaction",
        detail={"old_transaction_id": str(old_txn) if old_txn else None},
        ip_address=ip_address,
    )

    return item


async def delete_item(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> None:
    """Delete a single vault item (DB row + storage file)."""
    item = await get_item(db, item_id=item_id, user_id=user_id)

    # Delete from storage
    storage = get_storage()
    await storage.delete(item.storage_key)

    # Log before deleting the row
    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="vault.deleted",
        entity_type="VaultItem",
        entity_id=item.id,
        action="delete",
        detail={"filename": item.filename, "storage_key": item.storage_key},
        ip_address=ip_address,
    )

    await db.delete(item)
    await db.flush()


async def delete_user_vault_items(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> int:
    """Hard-delete ALL vault items for a user (DB rows + storage files).

    Called during account deletion. Ship gate requirement.
    Returns count of items deleted.
    """
    # Load all items to get storage keys
    result = await db.execute(
        select(VaultItem).where(VaultItem.user_id == user_id)
    )
    items = list(result.scalars().all())

    if not items:
        return 0

    # Delete files from storage
    storage = get_storage()
    for item in items:
        await storage.delete(item.storage_key)

    # Hard-delete all DB rows
    await db.execute(
        delete(VaultItem).where(VaultItem.user_id == user_id)
    )
    await db.flush()

    return len(items)
