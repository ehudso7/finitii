"""Phase 8 delete integration: verify vault items are hard-deleted on account deletion."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserStatus
from app.models.vault import VaultItem
from app.services import delete_service, vault_service
from app.services.storage import InMemoryStorageBackend, set_storage, get_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    """Use in-memory storage for all tests."""
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield backend
    set_storage(None)


async def _create_user(db: AsyncSession) -> User:
    user = User(email="deletevault@test.com", password_hash="hash")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_delete_user_deletes_vault_items(db_session: AsyncSession):
    """Deleting a user hard-deletes all vault items and storage files."""
    user = await _create_user(db_session)
    storage = get_storage()

    # Upload 3 files
    keys = []
    for i in range(3):
        item = await vault_service.upload(
            db_session,
            user_id=user.id,
            filename=f"file{i}.jpg",
            content_type="image/jpeg",
            data=b"file data",
        )
        keys.append(item.storage_key)

    # Verify files exist
    for key in keys:
        assert await storage.exists(key)

    # Delete user
    result = await delete_service.delete_user_data(db_session, user_id=user.id)
    assert result is True

    # Verify all vault DB rows gone
    db_result = await db_session.execute(
        select(VaultItem).where(VaultItem.user_id == user.id)
    )
    assert len(list(db_result.scalars().all())) == 0

    # Verify all storage files gone
    for key in keys:
        assert not await storage.exists(key)

    # Verify user is soft-deleted
    user_result = await db_session.execute(
        select(User).where(User.id == user.id)
    )
    deleted_user = user_result.scalar_one()
    assert deleted_user.status == UserStatus.deleted


@pytest.mark.asyncio
async def test_delete_user_no_vault_items(db_session: AsyncSession):
    """Deleting a user with no vault items still succeeds."""
    user = await _create_user(db_session)
    result = await delete_service.delete_user_data(db_session, user_id=user.id)
    assert result is True
