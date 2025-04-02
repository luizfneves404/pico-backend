import contextlib
from typing import AsyncIterator

import redis.asyncio as redis

from app.config import settings

_redis: redis.Redis | None = None


def init() -> None:
    """Initialize the Redis connection.

    Args:
        redis_url: Redis connection URL
    """
    global _redis
    _redis = redis.from_url(settings.redis_url, decode_responses=True)


async def close() -> None:
    """Close the Redis connection if initialized."""
    global _redis
    if _redis is None:
        return
    await _redis.aclose()
    _redis = None


@contextlib.asynccontextmanager
async def use_redis() -> AsyncIterator[None]:
    """Use the Redis connection.

    Args:
        redis_url: Redis connection URL
    """
    try:
        init()
        yield
    finally:
        await close()


def get_redis() -> redis.Redis:
    """Get the Redis connection.

    Returns:
        The Redis connection

    Raises:
        IOError: If the Redis connection is not initialized
    """
    if _redis is None:
        raise IOError("Redis connection is not initialized")
    return _redis
