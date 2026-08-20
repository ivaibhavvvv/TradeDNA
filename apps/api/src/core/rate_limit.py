"""TradeDNA Phase 8D-B - Tiered Rate Limiting System.
Provides sliding-window rate limiting with distinct security tiers:
- AUTH: Sensitive authentication endpoints (login, register, refresh)
- PAIRING: Ephemeral token generation and device handshake
- DASHBOARD: Authenticated BFF analytics queries
- INGRESS: High-frequency MT5 connector heartbeats and deal synchronizations (300 req/min)
"""

import time
from collections import defaultdict
from typing import Callable, Optional
from fastapi import Request, Response
from src.core.config import get_settings
from src.core.exceptions import TradeDNAException

settings = get_settings()


class RateLimitExceededException(TradeDNAException):
    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        retry_after: int = 60,
    ):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )


class InMemoryRateLimiter:
    """Thread-safe sliding window rate limiter with tiered quotas."""

    def __init__(self):
        # key -> list of float timestamps
        self._records: dict[str, list[float]] = defaultdict(list)
        self.force_enabled: bool = False

    def reset(self) -> None:
        self._records.clear()

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[int, int, int]:
        """
        Check rate limit for a given key.
        Returns (remaining_requests, reset_after_seconds, max_requests).
        Raises RateLimitExceededException if exceeded.
        """
        if settings.ENVIRONMENT == "testing" and not self.force_enabled:
            return max_requests, 0, max_requests

        now = time.time()
        window_start = now - window_seconds

        # Clean expired timestamps
        timestamps = [t for t in self._records[key] if t > window_start]
        self._records[key] = timestamps

        if len(timestamps) >= max_requests:
            oldest = timestamps[0]
            retry_after = int(max(1, (oldest + window_seconds) - now))
            raise RateLimitExceededException(
                message=f"Rate limit exceeded: quota of {max_requests} requests per {window_seconds}s reached. Try again in {retry_after}s.",
                retry_after=retry_after,
            )

        self._records[key].append(now)
        remaining = max(0, max_requests - len(self._records[key]))
        reset_after = window_seconds
        return remaining, reset_after, max_requests


rate_limiter = InMemoryRateLimiter()


def rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    tier: str = "STANDARD",
    key_func: Optional[Callable[[Request], str]] = None,
):
    """
    FastAPI route dependency to apply rate limiting.
    Supports custom key resolvers (IP, Tenant, Device ID, User ID) and attaches
    standard rate-limit tracking headers.
    """
    async def dependency(request: Request, response: Response):
        if key_func:
            key = key_func(request)
        else:
            client_ip = request.client.host if request.client else "unknown"
            path = request.url.path
            key = f"{tier}:{client_ip}:{path}"

        remaining, reset_after, limit = rate_limiter.check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_after)

    return dependency
