from app.services.storage.base import StorageBackend
from app.services.storage.local import LocalFileStorage

_storage_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Factory function returning the configured storage backend.
    
    Currently returns LocalFileStorage. Can be extended to return
    S3Storage, AzureBlobStorage, etc. based on settings.
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalFileStorage()
    return _storage_instance
