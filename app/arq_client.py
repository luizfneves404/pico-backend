import contextlib
import logging
from typing import Any, AsyncIterator

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

_redis: ArqRedis | None = None

logger = logging.getLogger(__name__)


async def init(url: str) -> None:
    """Initialize the ARQ Redis connection pool.

    Args:
        redis_url: Redis connection URL
    """
    global _redis
    _redis = await create_pool(RedisSettings.from_dsn(url))


async def close() -> None:
    """Close the ARQ Redis connection pool if initialized."""
    global _redis
    if _redis is None:
        return
    await _redis.aclose()
    _redis = None


@contextlib.asynccontextmanager
async def arq_redis(url: str) -> AsyncIterator[None]:
    """Use the ARQ Redis connection pool.

    Args:
        redis_url: Redis connection URL
    """
    global _redis
    try:
        await init(url)
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
    Don't call this in a for loop if it's a lot of jobs! Use asyncio.gather instead:
    ```
    await asyncio.gather(
        *(enqueue_job("task", item) for item in items)
    )
    ```

    Args:
        function: The name of the function to execute
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
    """
    client = _get_redis()

    # Strip args and kwargs if too big for logging
    def truncate_if_large(obj: Any, max_length: int = 400) -> str:
        obj_str = str(obj)
        if len(obj_str) > max_length:
            return obj_str[:max_length] + "... (truncated)"
        return obj_str

    args_str = truncate_if_large(args)
    kwargs_str = truncate_if_large(kwargs)

    logger.info(
        f"Enqueuing job {function} with args {args_str} and kwargs {kwargs_str}"
    )
    await client.enqueue_job(function, *args, **kwargs)


async def clear_redis() -> None:
    """Clear the Redis connection pool."""
    client = _get_redis()
    await client.flushall()
