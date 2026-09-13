from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract base class for file storage backends."""

    @abstractmethod
    async def save(self, key: str, data: bytes) -> str:
        """Save file data under the given key. Returns the storage key."""
        ...

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """Read file data by key."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete file by key."""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a file exists at the given key."""
        ...
