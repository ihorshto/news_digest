"""arq worker entrypoint: `arq app.worker.main.WorkerSettings`."""

import logging

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


async def schedule_tick(ctx: dict) -> int:
    logger.info("schedule tick")
    return 0


async def startup(ctx: dict) -> None:
    setup_logging()
    get_settings().log_fake_modes()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions: list = []
    cron_jobs = [cron(schedule_tick, minute=set(range(0, 60, 5)), run_at_startup=True)]
    on_startup = startup
