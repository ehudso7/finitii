"""Storage abstraction for vault file storage.

Phase 8: Vault — receipts & documents lite.

Provides a pluggable storage backend. Default is local filesystem.
No public access — files are served only through authenticated API endpoints.
"""

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """Abstract storage backend for vault files."""

    @abstractmethod
    async def save(self, key: str, data: bytes, content_type: str) -> str:
        """Save file data. Returns the storage key."""
        ...

    @abstractmethod
    async def load(self, key: str) -> bytes:
        """Load file data by key. Raises FileNotFoundError if missing."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete file by key. No-op if not found."""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        ...


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage. Files stored in a private directory.

    Not suitable for production multi-server deployments,
    but works for MVP single-server and testing.
    """

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            base_dir = os.environ.get("VAULT_STORAGE_DIR", "/tmp/finitii-vault")
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Sanitize key to prevent path traversal
        safe_key = key.replace("..", "").replace("/", "_").replace("\\", "_")
        return self._base_dir / safe_key

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.write_bytes(data)
        return key

    async def load(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


class InMemoryStorageBackend(StorageBackend):
    """In-memory storage for testing. No disk I/O."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        self._store[key] = data
        return key

    async def load(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(f"File not found: {key}")
        return self._store[key]

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store


def generate_storage_key(user_id: uuid.UUID, filename: str) -> str:
    """Generate a unique storage key for a vault file.

    Format: {user_id}_{uuid4}_{sanitized_filename}
    """
    safe_name = "".join(
        c if c.isalnum() or c in (".", "-", "_") else "_"
        for c in filename
    )[:100]
    return f"{user_id}_{uuid.uuid4().hex}_{safe_name}"


# Module-level singleton — can be replaced for testing
_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Get the current storage backend."""
    global _storage
    if _storage is None:
        _storage = LocalStorageBackend()
    return _storage


def set_storage(backend: StorageBackend) -> None:
    """Set the storage backend (used for testing)."""
    global _storage
    _storage = backend
