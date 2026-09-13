import os
import aiofiles
from pathlib import Path

from app.services.storage.base import StorageBackend
from app.core.config import settings
from app.core.logging import logger


class LocalFileStorage(StorageBackend):
    """Local filesystem storage backend for development."""

    def __init__(self, base_path: str | None = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _full_path(self, key: str) -> Path:
        """Resolve the full filesystem path for a storage key, preventing traversal."""
        full = (self.base_path / key).resolve()
        # Prevent path traversal attacks
        if not str(full).startswith(str(self.base_path)):
            raise ValueError("Invalid storage key: path traversal detected")
        return full

    async def save(self, key: str, data: bytes) -> str:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        logger.info(f"Stored file: key={key}, size={len(data)} bytes")
        return key

    async def read(self, key: str) -> bytes:
        path = self._full_path(key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        path = self._full_path(key)
        if path.exists():
            os.remove(path)
            logger.info(f"Deleted file: key={key}")
            # Clean up empty parent directories
            try:
                path.parent.rmdir()
            except OSError:
                pass  # Directory not empty, that's fine

    async def exists(self, key: str) -> bool:
        return self._full_path(key).exists()
