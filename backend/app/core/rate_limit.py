import time
import asyncio
from typing import Dict, List, Tuple
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.logging import logger


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter.
    
    Tracks request timestamps per client/resource key and enforces rate limits.
    Designed with a clean interface that can be backed by Redis in future phases.
    """

    def __init__(self):
        self._requests: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, limit: int, window_seconds: int = 60) -> Tuple[bool, int]:
        """Check if request is within allowed rate limit.
        
        Returns:
            Tuple of (is_allowed: bool, retry_after_seconds: int)
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0

        now = time.time()
        window_start = now - window_seconds

        async with self._lock:
            # Retrieve or initialize timestamp list
            timestamps = self._requests.get(key, [])
            # Evict timestamps outside current window
            valid_timestamps = [t for t in timestamps if t > window_start]

            if len(valid_timestamps) >= limit:
                # Rate limit exceeded
                oldest_timestamp = valid_timestamps[0]
                retry_after = max(1, int(window_seconds - (now - oldest_timestamp)))
                self._requests[key] = valid_timestamps
                return False, retry_after

            # Append current request
            valid_timestamps.append(now)
            self._requests[key] = valid_timestamps
            return True, 0

    async def check(self, key: str, limit: int, window_seconds: int = 60):
        """Raise HTTPException 429 if rate limit is exceeded."""
        allowed, retry_after = await self.is_allowed(key, limit, window_seconds)
        if not allowed:
            logger.warning(
                f"Rate limit exceeded for key='{key}': {limit} reqs per {window_seconds}s. "
                f"Retry-After: {retry_after}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    def clear(self):
        """Reset rate limiter state (useful for test isolation)."""
        self._requests.clear()


rate_limiter = InMemoryRateLimiter()
