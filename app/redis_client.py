import redis.asyncio as redis


class RedisManager:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    def init(self, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._redis is None:
            return
        await self._redis.aclose()
        self._redis = None

    def get_redis(self) -> redis.Redis:
        if self._redis is None:
            raise IOError("RedisManager is not initialized")
        return self._redis


redis_manager = RedisManager()


async def get_redis_client() -> redis.Redis:
    """
    This function is used to get a redis client.
    """
    return redis_manager.get_redis()
