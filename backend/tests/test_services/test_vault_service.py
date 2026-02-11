"""Phase 8 service tests: vault service (upload, list, get, link, delete)."""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit import AuditLogEvent
from app.models.user import User
from app.models.vault import VaultItem
from app.services import vault_service
from app.services.storage import InMemoryStorageBackend, set_storage, get_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    """Use in-memory storage for all vault tests."""
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield backend
    set_storage(None)


async def _create_user(db: AsyncSession, email: str = "vault@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


# --- upload ---

@pytest.mark.asyncio
async def test_upload(db_session: AsyncSession):
    """Upload stores file and creates DB record."""
    user = await _create_user(db_session)
    item = await vault_service.upload(
        db_session,
        user_id=user.id,
        filename="receipt.jpg",
        content_type="image/jpeg",
        data=b"fake image data",
        item_type="receipt",
        description="Lunch",
    )
    assert item.id is not None
    assert item.filename == "receipt.jpg"
    assert item.content_type == "image/jpeg"
    assert item.file_size == len(b"fake image data")
    assert item.item_type.value == "receipt"
    assert item.description == "Lunch"
    assert item.storage_key is not None

    # Verify file in storage
    storage = get_storage()
    data = await storage.load(item.storage_key)
    assert data == b"fake image data"


@pytest.mark.asyncio
async def test_upload_with_transaction(db_session: AsyncSession):
    """Upload can link to transaction at upload time."""
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    user = await _create_user(db_session)
    account = Account(
        user_id=user.id, institution_name="Bank", account_name="Check",
        account_type="checking", currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        account_id=account.id, user_id=user.id,
        raw_description="Test", normalized_description="test",
        amount=25.00, transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()

    item = await vault_service.upload(
        db_session,
        user_id=user.id,
        filename="receipt.png",
        content_type="image/png",
        data=b"png data",
        transaction_id=txn.id,
    )
    assert item.transaction_id == txn.id


@pytest.mark.asyncio
async def test_upload_too_large(db_session: AsyncSession):
    """Upload rejects files over MAX_FILE_SIZE."""
    user = await _create_user(db_session)
    big_data = b"x" * (vault_service.MAX_FILE_SIZE + 1)
    with pytest.raises(ValueError, match="too large"):
        await vault_service.upload(
            db_session,
            user_id=user.id,
            filename="huge.jpg",
            content_type="image/jpeg",
            data=big_data,
        )


@pytest.mark.asyncio
async def test_upload_invalid_content_type(db_session: AsyncSession):
    """Upload rejects unsupported content types."""
    user = await _create_user(db_session)
    with pytest.raises(ValueError, match="Unsupported file type"):
        await vault_service.upload(
            db_session,
            user_id=user.id,
            filename="script.js",
            content_type="application/javascript",
            data=b"alert(1)",
        )


@pytest.mark.asyncio
async def test_upload_invalid_item_type(db_session: AsyncSession):
    """Upload rejects invalid item_type."""
    user = await _create_user(db_session)
    with pytest.raises(ValueError, match="Invalid item_type"):
        await vault_service.upload(
            db_session,
            user_id=user.id,
            filename="file.jpg",
            content_type="image/jpeg",
            data=b"data",
            item_type="spreadsheet",
        )


@pytest.mark.asyncio
async def test_upload_document_type(db_session: AsyncSession):
    """Upload supports document item_type."""
    user = await _create_user(db_session)
    item = await vault_service.upload(
        db_session,
        user_id=user.id,
        filename="statement.pdf",
        content_type="application/pdf",
        data=b"pdf data",
        item_type="document",
    )
    assert item.item_type.value == "document"


@pytest.mark.asyncio
async def test_upload_audit_logged(db_session: AsyncSession):
    """Upload is audit-logged."""
    user = await _create_user(db_session)
    await vault_service.upload(
        db_session,
        user_id=user.id,
        filename="audit.jpg",
        content_type="image/jpeg",
        data=b"data",
    )
    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "vault.uploaded",
        )
    )
    event = result.scalar_one()
    assert event.detail["filename"] == "audit.jpg"


# --- list_items ---

@pytest.mark.asyncio
async def test_list_items(db_session: AsyncSession):
    """List returns all user's vault items."""
    user = await _create_user(db_session)
    for i in range(3):
        await vault_service.upload(
            db_session,
            user_id=user.id,
            filename=f"file{i}.jpg",
            content_type="image/jpeg",
            data=b"data",
        )
    items = await vault_service.list_items(db_session, user_id=user.id)
    assert len(items) == 3


@pytest.mark.asyncio
async def test_list_items_filter_type(db_session: AsyncSession):
    """List filters by item_type."""
    user = await _create_user(db_session)
    await vault_service.upload(
        db_session, user_id=user.id,
        filename="receipt.jpg", content_type="image/jpeg",
        data=b"data", item_type="receipt",
    )
    await vault_service.upload(
        db_session, user_id=user.id,
        filename="doc.pdf", content_type="application/pdf",
        data=b"data", item_type="document",
    )
    receipts = await vault_service.list_items(
        db_session, user_id=user.id, item_type="receipt"
    )
    assert len(receipts) == 1
    assert receipts[0].filename == "receipt.jpg"


@pytest.mark.asyncio
async def test_list_items_user_isolation(db_session: AsyncSession):
    """User can only see their own vault items."""
    user1 = await _create_user(db_session, email="user1@test.com")
    user2 = await _create_user(db_session, email="user2@test.com")
    await vault_service.upload(
        db_session, user_id=user1.id,
        filename="u1.jpg", content_type="image/jpeg", data=b"data",
    )
    await vault_service.upload(
        db_session, user_id=user2.id,
        filename="u2.jpg", content_type="image/jpeg", data=b"data",
    )
    items1 = await vault_service.list_items(db_session, user_id=user1.id)
    assert len(items1) == 1
    assert items1[0].filename == "u1.jpg"


# --- get_item ---

@pytest.mark.asyncio
async def test_get_item(db_session: AsyncSession):
    """Get a single vault item."""
    user = await _create_user(db_session)
    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="get.jpg", content_type="image/jpeg", data=b"data",
    )
    fetched = await vault_service.get_item(
        db_session, item_id=item.id, user_id=user.id
    )
    assert fetched.id == item.id


@pytest.mark.asyncio
async def test_get_item_not_found(db_session: AsyncSession):
    """Get non-existent item raises ValueError."""
    user = await _create_user(db_session)
    with pytest.raises(ValueError, match="not found"):
        await vault_service.get_item(
            db_session, item_id=uuid.uuid4(), user_id=user.id
        )


@pytest.mark.asyncio
async def test_get_item_wrong_user(db_session: AsyncSession):
    """Get item belonging to other user raises ValueError."""
    user1 = await _create_user(db_session, email="owner@test.com")
    user2 = await _create_user(db_session, email="other@test.com")
    item = await vault_service.upload(
        db_session, user_id=user1.id,
        filename="private.jpg", content_type="image/jpeg", data=b"data",
    )
    with pytest.raises(ValueError, match="not found"):
        await vault_service.get_item(
            db_session, item_id=item.id, user_id=user2.id
        )


# --- get_file_data ---

@pytest.mark.asyncio
async def test_get_file_data(db_session: AsyncSession):
    """Download returns item metadata and file bytes."""
    user = await _create_user(db_session)
    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="download.jpg", content_type="image/jpeg",
        data=b"file bytes here",
    )
    fetched, data = await vault_service.get_file_data(
        db_session, item_id=item.id, user_id=user.id
    )
    assert fetched.id == item.id
    assert data == b"file bytes here"


# --- link_to_transaction ---

@pytest.mark.asyncio
async def test_link_to_transaction(db_session: AsyncSession):
    """Link vault item to a transaction."""
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    user = await _create_user(db_session)
    account = Account(
        user_id=user.id, institution_name="Bank", account_name="Check",
        account_type="checking", currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        account_id=account.id, user_id=user.id,
        raw_description="Test", normalized_description="test",
        amount=25.00, transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()

    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="link.jpg", content_type="image/jpeg", data=b"data",
    )
    assert item.transaction_id is None

    linked = await vault_service.link_to_transaction(
        db_session, item_id=item.id, user_id=user.id,
        transaction_id=txn.id,
    )
    assert linked.transaction_id == txn.id


@pytest.mark.asyncio
async def test_link_audit_logged(db_session: AsyncSession):
    """Linking is audit-logged."""
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    user = await _create_user(db_session)
    account = Account(
        user_id=user.id, institution_name="Bank", account_name="Check",
        account_type="checking", currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        account_id=account.id, user_id=user.id,
        raw_description="Test", normalized_description="test",
        amount=10.00, transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()

    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="laud.jpg", content_type="image/jpeg", data=b"data",
    )
    await vault_service.link_to_transaction(
        db_session, item_id=item.id, user_id=user.id,
        transaction_id=txn.id,
    )
    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "vault.linked",
        )
    )
    assert result.scalar_one() is not None


# --- unlink_transaction ---

@pytest.mark.asyncio
async def test_unlink_transaction(db_session: AsyncSession):
    """Unlink removes transaction reference."""
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    user = await _create_user(db_session)
    account = Account(
        user_id=user.id, institution_name="Bank", account_name="Check",
        account_type="checking", currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        account_id=account.id, user_id=user.id,
        raw_description="Test", normalized_description="test",
        amount=10.00, transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()

    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="unlink.jpg", content_type="image/jpeg", data=b"data",
        transaction_id=txn.id,
    )
    assert item.transaction_id is not None

    unlinked = await vault_service.unlink_transaction(
        db_session, item_id=item.id, user_id=user.id,
    )
    assert unlinked.transaction_id is None


# --- delete_item ---

@pytest.mark.asyncio
async def test_delete_item(db_session: AsyncSession):
    """Delete removes DB row and storage file."""
    user = await _create_user(db_session)
    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="delete.jpg", content_type="image/jpeg", data=b"data",
    )
    storage_key = item.storage_key
    storage = get_storage()
    assert await storage.exists(storage_key)

    await vault_service.delete_item(
        db_session, item_id=item.id, user_id=user.id,
    )

    # DB row gone
    with pytest.raises(ValueError, match="not found"):
        await vault_service.get_item(
            db_session, item_id=item.id, user_id=user.id
        )

    # Storage file gone
    assert not await storage.exists(storage_key)


@pytest.mark.asyncio
async def test_delete_audit_logged(db_session: AsyncSession):
    """Deletion is audit-logged."""
    user = await _create_user(db_session)
    item = await vault_service.upload(
        db_session, user_id=user.id,
        filename="daud.jpg", content_type="image/jpeg", data=b"data",
    )
    await vault_service.delete_item(
        db_session, item_id=item.id, user_id=user.id,
    )
    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "vault.deleted",
        )
    )
    event = result.scalar_one()
    assert event.detail["filename"] == "daud.jpg"


# --- delete_user_vault_items ---

@pytest.mark.asyncio
async def test_delete_user_vault_items(db_session: AsyncSession):
    """Hard-delete all vault items for a user."""
    user = await _create_user(db_session)
    storage = get_storage()
    keys = []
    for i in range(3):
        item = await vault_service.upload(
            db_session, user_id=user.id,
            filename=f"file{i}.jpg", content_type="image/jpeg", data=b"data",
        )
        keys.append(item.storage_key)

    count = await vault_service.delete_user_vault_items(
        db_session, user_id=user.id
    )
    assert count == 3

    # All DB rows gone
    items = await vault_service.list_items(db_session, user_id=user.id)
    assert len(items) == 0

    # All storage files gone
    for key in keys:
        assert not await storage.exists(key)


@pytest.mark.asyncio
async def test_delete_user_vault_items_empty(db_session: AsyncSession):
    """Deleting with no vault items returns 0."""
    user = await _create_user(db_session)
    count = await vault_service.delete_user_vault_items(
        db_session, user_id=user.id
    )
    assert count == 0
