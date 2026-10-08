from typing import Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

PROCESS_TOPIC = "process_topic"


class JobQueue(Protocol):
    async def enqueue_job(self, function: str, *args, _job_id: str | None = None, **kwargs): ...


_pool: ArqRedis | None = None


async def get_queue() -> JobQueue:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_topic_run(queue: JobQueue, topic_id: int, run_key: str, manual: bool) -> bool:
    """Enqueue processing of one topic. The job id doubles as an idempotency key:
    arq refuses a second job with the same id while the first one is queued,
    running, or its result is retained."""
    job = await queue.enqueue_job(
        PROCESS_TOPIC, topic_id, run_key, manual, _job_id=f"topic:{topic_id}:{run_key}"
    )
    return job is not None
