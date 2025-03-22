from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class ArqClientManager:
    def __init__(self) -> None:
        self._redis: ArqRedis | None = None

    async def init(self, redis_url: str) -> None:
        self._redis = await create_pool(RedisSettings.from_dsn(redis_url))

    async def close(self) -> None:
        if self._redis is None:
            return
        await self._redis.aclose()
        self._redis = None

    def get_redis(self) -> ArqRedis:
        if self._redis is None:
            raise IOError("ArqClientManager is not initialized")
        return self._redis


arq_client_manager = ArqClientManager()


async def enqueue_job(function: str, *args: Any, **kwargs: Any) -> None:
    client = await arq_client_manager.get_redis()
    await client.enqueue_job(function, *args, **kwargs)
