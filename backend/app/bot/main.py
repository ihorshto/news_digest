"""Telegram bot entrypoint (long polling): `python -m app.bot.main`."""

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is empty: bot is idle (fake mode)")
        await asyncio.Event().wait()  # keep the container alive without polling


if __name__ == "__main__":
    asyncio.run(main())
