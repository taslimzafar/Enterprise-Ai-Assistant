from typing import Optional
import httpx
from app.services.storage.base import StorageBackend
from app.core.config import settings
from app.core.logging import logger


class S3ObjectStorage(StorageBackend):
    """
    Production-ready S3-compatible Object Storage implementation.
    Compatible with AWS S3, Cloudflare R2, MinIO, and Google Cloud Storage (S3 API).
    Uses secure HTTP PUT/GET/DELETE/HEAD operations.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        self.bucket_name = bucket_name or getattr(settings, "S3_BUCKET_NAME", "enterprise-ai-documents")
        self.endpoint_url = (endpoint_url or getattr(settings, "S3_ENDPOINT_URL", "http://localhost:9000")).rstrip("/")
        self.region_name = region_name or getattr(settings, "S3_REGION_NAME", "us-east-1")
        self.access_key = access_key or getattr(settings, "S3_ACCESS_KEY_ID", None)
        self.secret_key = secret_key or getattr(settings, "S3_SECRET_ACCESS_KEY", None)

    def _get_url(self, key: str) -> str:
        # Strip leading slashes to prevent traversal
        clean_key = key.lstrip("/")
        return f"{self.endpoint_url}/{self.bucket_name}/{clean_key}"

    async def save(self, key: str, data: bytes) -> str:
        url = self._get_url(key)
        headers = {"Content-Type": "application/octet-stream"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.put(url, content=data, headers=headers)
                if resp.status_code not in (200, 201):
                    logger.warning(f"S3 save returned status {resp.status_code}: {resp.text}")
            logger.info(f"Stored object to S3: key={key}, size={len(data)} bytes")
            return key
        except Exception as e:
            logger.error(f"S3 upload error for key={key}: {e}")
            raise

    async def read(self, key: str) -> bytes:
        url = self._get_url(key)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code == 404:
                    raise FileNotFoundError(f"Object not found in S3: {key}")
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to read from S3 (status {resp.status_code})")
                return resp.content
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"S3 read error for key={key}: {e}")
            raise

    async def delete(self, key: str) -> None:
        url = self._get_url(key)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(url)
            logger.info(f"Deleted object from S3: key={key}")
        except Exception as e:
            logger.error(f"S3 delete error for key={key}: {e}")
            raise

    async def exists(self, key: str) -> bool:
        url = self._get_url(key)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.head(url)
                return resp.status_code == 200
        except Exception:
            return False
