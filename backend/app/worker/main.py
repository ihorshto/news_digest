"""arq worker entrypoint: `arq app.worker.main.WorkerSettings`."""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from arq import Retry, cron, func
from arq.connections import RedisSettings
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.queue import PROCESS_TOPIC, JobQueue, enqueue_topic_run
from app.db.base import utcnow
from app.db.session import make_engine, make_sessionmaker
from app.models import Topic
from app.services.collectors.tavily import get_tavily
from app.services.embeddings import get_embedder
from app.services.llm import get_llm_client
from app.services.pipeline import PipelineDeps, process_topic
from app.services.schedule import compute_next_run
from app.services.telegram import FakeTelegramSender, HttpTelegramSender

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 15 * 60


def slot_run_key(next_run_at: datetime) -> str:
    """Stable id of a schedule slot; the same slot always maps to the same job id."""
    return "slot-" + next_run_at.astimezone(UTC).strftime("%Y%m%dT%H%M")


async def enqueue_due_topics(sessionmaker, queue: JobQueue, now: datetime) -> int:
    async with sessionmaker() as db:
        topics = (
            await db.scalars(
                select(Topic)
                .where(
                    Topic.is_active.is_(True),
                    or_(Topic.next_run_at <= now, Topic.next_run_at.is_(None)),
                )
                .options(selectinload(Topic.user))
            )
        ).all()
        enqueued = 0
        for topic in topics:
            if topic.next_run_at is None:
                topic.next_run_at = compute_next_run(
                    topic.frequency, topic.send_hour, topic.weekday, topic.user.timezone, now
                )
                continue
            if await enqueue_topic_run(queue, topic.id, slot_run_key(topic.next_run_at), False):
                enqueued += 1
        await db.commit()
    return enqueued


async def schedule_tick(ctx: dict) -> int:
    count = await enqueue_due_topics(ctx["sessionmaker"], ctx["redis"], utcnow())
    if count:
        logger.info("schedule tick: enqueued %d topic run(s)", count)
    return count


async def _mark_failed(sessionmaker, topic_id: int, manual: bool, error: str) -> None:
    async with sessionmaker() as db:
        topic = await db.scalar(
            select(Topic).where(Topic.id == topic_id).options(selectinload(Topic.user))
        )
        if topic is None:
            return
        topic.last_run_status = f"error: {error}"[:255]
        if not manual:
            # Do not retry the same failing slot forever; move on to the next one.
            topic.next_run_at = compute_next_run(
                topic.frequency, topic.send_hour, topic.weekday, topic.user.timezone, utcnow()
            )
        await db.commit()


async def process_topic_job(ctx: dict, topic_id: int, run_key: str, manual: bool = False) -> dict:
    redis = ctx["redis"]
    lock_key, token = f"lock:topic:{topic_id}", uuid.uuid4().hex
    if not await redis.set(lock_key, token, nx=True, ex=LOCK_TIMEOUT_SECONDS):
        logger.info("topic %s is being processed by another job; retrying later", topic_id)
        raise Retry(defer=30)
    try:
        result = await process_topic(ctx["deps"], topic_id, run_key, manual)
        return {"status": result.status, "digest_id": result.digest_id, **result.details}
    except Exception as exc:
        logger.exception("topic %s run %s failed", topic_id, run_key)
        await _mark_failed(ctx["sessionmaker"], topic_id, manual, str(exc))
        return {"status": "error", "error": str(exc)[:500]}
    finally:
        # Release only our own lock (it may have expired and been taken by another job).
        held = await redis.get(lock_key)
        if held in (token, token.encode()):
            await redis.delete(lock_key)


async def startup(ctx: dict) -> None:
    setup_logging()
    logging.getLogger("arq").propagate = False  # arq has its own handler
    settings = get_settings()
    settings.log_fake_modes()
    engine = make_engine()
    ctx["engine"] = engine
    ctx["sessionmaker"] = sessionmaker = make_sessionmaker(engine)
    http = httpx.AsyncClient(timeout=settings.http_timeout_seconds, follow_redirects=True)
    ctx["http"] = http
    telegram = (
        FakeTelegramSender()
        if settings.fake_telegram
        else HttpTelegramSender(settings.telegram_bot_token, http)
    )
    ctx["deps"] = PipelineDeps(
        sessionmaker=sessionmaker,
        settings=settings,
        llm=get_llm_client(settings),
        embedder=get_embedder(settings),
        tavily=get_tavily(settings),
        telegram=telegram,
        http=http,
    )
    logger.info("worker ready")


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()
    await ctx["engine"].dispose()


def _tick_minutes() -> set[int]:
    step = get_settings().schedule_tick_minutes
    return set(range(0, 60, step))


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [func(process_topic_job, name=PROCESS_TOPIC)]
    cron_jobs = [
        cron(schedule_tick, minute=_tick_minutes(), run_at_startup=True, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = 600
    max_jobs = 4
    max_tries = 5
    keep_result = 3600
