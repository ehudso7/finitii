"""Phase 8 model tests: VaultItem."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.vault import VaultItem, VaultItemType


async def _create_user(db: AsyncSession) -> User:
    user = User(email="p8model@test.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_vault_item_create(db_session: AsyncSession):
    """VaultItem stores all metadata fields."""
    user = await _create_user(db_session)
    item = VaultItem(
        user_id=user.id,
        filename="receipt.jpg",
        content_type="image/jpeg",
        file_size=1024,
        item_type=VaultItemType.receipt,
        storage_key="test_key_123",
        description="Lunch receipt",
    )
    db_session.add(item)
    await db_session.flush()

    assert item.id is not None
    assert item.user_id == user.id
    assert item.filename == "receipt.jpg"
    assert item.content_type == "image/jpeg"
    assert item.file_size == 1024
    assert item.item_type == VaultItemType.receipt
    assert item.storage_key == "test_key_123"
    assert item.description == "Lunch receipt"
    assert item.transaction_id is None
    assert item.uploaded_at is not None


@pytest.mark.asyncio
async def test_vault_item_type_enum():
    """VaultItemType has receipt and document."""
    assert VaultItemType.receipt.value == "receipt"
    assert VaultItemType.document.value == "document"
    assert len(VaultItemType) == 2


@pytest.mark.asyncio
async def test_vault_item_unique_storage_key(db_session: AsyncSession):
    """VaultItem enforces unique storage_key."""
    user = await _create_user(db_session)
    for i in range(2):
        db_session.add(VaultItem(
            user_id=user.id,
            filename=f"file{i}.jpg",
            content_type="image/jpeg",
            file_size=100,
            item_type=VaultItemType.receipt,
            storage_key="duplicate_key",
        ))
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_vault_item_nullable_transaction(db_session: AsyncSession):
    """VaultItem can exist without a transaction_id."""
    user = await _create_user(db_session)
    item = VaultItem(
        user_id=user.id,
        filename="doc.pdf",
        content_type="application/pdf",
        file_size=2048,
        item_type=VaultItemType.document,
        storage_key="doc_key_456",
    )
    db_session.add(item)
    await db_session.flush()

    assert item.transaction_id is None


@pytest.mark.asyncio
async def test_vault_item_with_transaction(db_session: AsyncSession):
    """VaultItem can be linked to a transaction."""
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    user = await _create_user(db_session)
    account = Account(
        user_id=user.id,
        institution_name="Test Bank",
        account_name="Checking",
        account_type="checking",
        currency="USD",
    )
    db_session.add(account)
    await db_session.flush()

    txn = Transaction(
        account_id=account.id,
        user_id=user.id,
        raw_description="Test",
        normalized_description="test",
        amount=50.00,
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()

    item = VaultItem(
        user_id=user.id,
        transaction_id=txn.id,
        filename="receipt.png",
        content_type="image/png",
        file_size=512,
        item_type=VaultItemType.receipt,
        storage_key="linked_key_789",
    )
    db_session.add(item)
    await db_session.flush()

    assert item.transaction_id == txn.id
