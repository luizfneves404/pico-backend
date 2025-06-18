import contextlib
from typing import Any, AsyncIterator

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings

_redis: ArqRedis | None = None

logger = logging.getLogger(__name__)


async def init() -> None:
    """Initialize the ARQ Redis connection pool.

    Args:
        redis_url: Redis connection URL
    """
    global _redis
    _redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def close() -> None:
    """Close the ARQ Redis connection pool if initialized."""
    global _redis
    if _redis is None:
        return
    await _redis.aclose()
    _redis = None


@contextlib.asynccontextmanager
async def arq_redis() -> AsyncIterator[None]:
    """Use the ARQ Redis connection pool.

    Args:
        redis_url: Redis connection URL
    """
    global _redis
    try:
        await init()
        yield
    finally:
        await close()


def _get_redis() -> ArqRedis:
    """Get the ARQ Redis connection.

    Returns:
        The ARQ Redis connection

    Raises:
        IOError: If the ARQ Redis connection is not initialized
    """
    if _redis is None:
        raise IOError("ARQ Redis connection is not initialized")
    return _redis


async def enqueue_job(function: str, *args: Any, **kwargs: Any) -> None:
    """Enqueue a job to be processed by the ARQ worker.

    Args:
        function: The name of the function to execute
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
    """
    client = _get_redis()
    logger.info(f"Enqueuing job {function} with args {args} and kwargs {kwargs}")
    await client.enqueue_job(function, *args, **kwargs)


async def clear_redis() -> None:
    """Clear the Redis connection pool."""
    client = _get_redis()
    await client.flushall()
