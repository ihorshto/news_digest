from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def hit_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int = 60) -> bool:
    """Fixed-window counter. Returns True when the request must be rejected."""
    full_key = f"rl:{key}"
    count = await redis.incr(full_key)
    if count == 1:
        await redis.expire(full_key, window_seconds)
    return count > limit
