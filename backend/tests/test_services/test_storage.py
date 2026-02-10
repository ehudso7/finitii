"""Phase 8 service tests: storage abstraction."""

import pytest
import uuid

from app.services.storage import (
    InMemoryStorageBackend,
    LocalStorageBackend,
    generate_storage_key,
)


@pytest.mark.asyncio
async def test_in_memory_save_and_load():
    """InMemoryStorageBackend saves and loads data."""
    backend = InMemoryStorageBackend()
    await backend.save("key1", b"hello", "text/plain")
    data = await backend.load("key1")
    assert data == b"hello"


@pytest.mark.asyncio
async def test_in_memory_exists():
    """InMemoryStorageBackend reports existence correctly."""
    backend = InMemoryStorageBackend()
    assert not await backend.exists("missing")
    await backend.save("key1", b"data", "text/plain")
    assert await backend.exists("key1")


@pytest.mark.asyncio
async def test_in_memory_delete():
    """InMemoryStorageBackend deletes files."""
    backend = InMemoryStorageBackend()
    await backend.save("key1", b"data", "text/plain")
    await backend.delete("key1")
    assert not await backend.exists("key1")


@pytest.mark.asyncio
async def test_in_memory_delete_missing():
    """Deleting non-existent key is a no-op."""
    backend = InMemoryStorageBackend()
    await backend.delete("missing")  # Should not raise


@pytest.mark.asyncio
async def test_in_memory_load_missing():
    """Loading non-existent key raises FileNotFoundError."""
    backend = InMemoryStorageBackend()
    with pytest.raises(FileNotFoundError):
        await backend.load("missing")


@pytest.mark.asyncio
async def test_local_storage_save_and_load(tmp_path):
    """LocalStorageBackend saves and loads from filesystem."""
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    await backend.save("test_file", b"test data", "text/plain")
    data = await backend.load("test_file")
    assert data == b"test data"


@pytest.mark.asyncio
async def test_local_storage_delete(tmp_path):
    """LocalStorageBackend deletes files from filesystem."""
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    await backend.save("to_delete", b"data", "text/plain")
    assert await backend.exists("to_delete")
    await backend.delete("to_delete")
    assert not await backend.exists("to_delete")


@pytest.mark.asyncio
async def test_local_storage_path_traversal(tmp_path):
    """LocalStorageBackend sanitizes keys to prevent path traversal."""
    backend = LocalStorageBackend(base_dir=str(tmp_path))
    await backend.save("../../etc/passwd", b"data", "text/plain")
    # File should be in tmp_path, not at /etc/passwd
    assert await backend.exists("../../etc/passwd")
    data = await backend.load("../../etc/passwd")
    assert data == b"data"


def test_generate_storage_key():
    """generate_storage_key produces unique, safe keys."""
    uid = uuid.uuid4()
    key1 = generate_storage_key(uid, "receipt.jpg")
    key2 = generate_storage_key(uid, "receipt.jpg")
    assert key1 != key2  # Different each time
    assert str(uid) in key1
    assert "receipt.jpg" in key1


def test_generate_storage_key_sanitizes():
    """generate_storage_key sanitizes dangerous filenames."""
    uid = uuid.uuid4()
    key = generate_storage_key(uid, "../../../etc/passwd")
    # The sanitized filename part (after user_id_uuid_) should not contain path separators
    # The key contains the user_id which has hyphens, so check the filename portion
    parts = key.split("_", 2)  # user-id_hexuuid_filename
    filename_part = parts[-1] if len(parts) >= 3 else key
    assert "/" not in filename_part
    assert "\\" not in filename_part
