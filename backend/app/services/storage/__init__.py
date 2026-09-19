from app.services.storage.base import StorageBackend
from app.services.storage.local import LocalFileStorage
from app.services.storage.s3 import S3ObjectStorage
from app.core.config import settings

_storage_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Factory function returning the configured storage backend.
    
    Returns S3ObjectStorage when STORAGE_BACKEND == 's3',
    otherwise returns LocalFileStorage for local development.
    """
    global _storage_instance
    if _storage_instance is None:
        if getattr(settings, "STORAGE_BACKEND", "local").lower() == "s3":
            _storage_instance = S3ObjectStorage()
        else:
            _storage_instance = LocalFileStorage()
    return _storage_instance
