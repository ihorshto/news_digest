"""Telegram bot entrypoint (long polling): `python -m app.bot.main`.

The bot only handles incoming commands; digests are sent by the worker via the Bot API.
"""

import asyncio
import html
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis import get_redis
from app.db.session import get_sessionmaker
from app.models import Topic
from app.services.telegram_link import (
    BOT_USERNAME_KEY,
    LinkResult,
    link_chat,
    set_topic_active,
    topics_for_chat,
)

logger = logging.getLogger(__name__)

FREQUENCY_UK = {"hourly": "щогодини", "6h": "кожні 6 год", "daily": "щодня", "weekly": "щотижня"}


def site_url() -> str:
    return get_settings().public_base_url


def texts_start() -> str:
    return (
        "👋 Це бот <b>NewsDigest</b>: він надсилає короткі AI-дайджести новин за вашими темами.\n\n"
        f"1. Зареєструйтесь на сайті: {html.escape(site_url())}\n"
        "2. Натисніть «Підключити Telegram» — і повернетесь сюди вже з прив'язаним акаунтом.\n\n"
        "Команди: /topics — ваші теми, /pause і /resume — пауза та відновлення розсилки."
    )


NOT_LINKED = "Цей чат ще не прив'язаний до акаунта. Натисніть «Підключити Telegram» на сайті."


def topic_line(topic: Topic) -> str:
    state = "▶️ активна" if topic.is_active else "⏸ на паузі"
    return f"• <b>{html.escape(topic.name)}</b> — {FREQUENCY_UK.get(topic.frequency, '')}, {state}"


def keyboard(topics: list[Topic], only: bool | None = None) -> InlineKeyboardMarkup | None:
    """Buttons toggle each topic; `only` restricts to active (True) or paused (False)."""
    rows = []
    for topic in topics:
        if only is not None and topic.is_active != only:
            continue
        action = "pause" if topic.is_active else "resume"
        label = ("⏸ Пауза: " if topic.is_active else "▶️ Відновити: ") + topic.name[:40]
        rows.append([InlineKeyboardButton(text=label, callback_data=f"t:{action}:{topic.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def build_router(sessionmaker: async_sessionmaker[AsyncSession]) -> Router:
    router = Router()

    @router.message(CommandStart(deep_link=True))
    async def start_with_token(message: Message, command: CommandObject) -> None:
        async with sessionmaker() as db:
            result, user = await link_chat(
                db, command.args or "", message.chat.id, message.from_user.username
            )
        if result == LinkResult.linked:
            await message.answer(
                f"✅ Готово! Telegram прив'язано до акаунта <b>{html.escape(user.email)}</b>.\n"
                "Дайджести приходитимуть сюди. Список тем — /topics."
            )
        elif result == LinkResult.expired:
            await message.answer(
                "⌛ Посилання застаріло (діє 15 хвилин). Натисніть «Підключити Telegram» на сайті "
                "ще раз."
            )
        else:
            await message.answer("❌ Посилання недійсне або вже використане.\n\n" + texts_start())

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(texts_start())

    async def list_topics(message: Message, only: bool | None) -> None:
        async with sessionmaker() as db:
            user, topics = await topics_for_chat(db, message.chat.id)
        if user is None:
            await message.answer(NOT_LINKED)
            return
        if not topics:
            await message.answer(f"У вас ще немає тем. Створіть першу: {site_url()}/topics/new")
            return
        markup = keyboard(topics, only)
        lines = "\n".join(topic_line(t) for t in topics)
        hint = ""
        if only is True and markup is None:
            hint = "\n\nУсі теми вже на паузі."
        elif only is False and markup is None:
            hint = "\n\nНемає тем на паузі."
        await message.answer(f"Ваші теми:\n{lines}{hint}", reply_markup=markup)

    @router.message(Command("topics"))
    async def topics_cmd(message: Message) -> None:
        await list_topics(message, None)

    @router.message(Command("pause"))
    async def pause_cmd(message: Message) -> None:
        await list_topics(message, True)

    @router.message(Command("resume"))
    async def resume_cmd(message: Message) -> None:
        await list_topics(message, False)

    @router.callback_query(F.data.startswith("t:"))
    async def toggle(callback: CallbackQuery) -> None:
        try:
            _, action, raw_id = callback.data.split(":")
            topic_id = int(raw_id)
        except ValueError:
            await callback.answer("Некоректна дія")
            return
        chat_id = callback.message.chat.id if callback.message else callback.from_user.id
        async with sessionmaker() as db:
            topic = await set_topic_active(db, chat_id, topic_id, active=(action == "resume"))
            if topic is None:
                await callback.answer("Тему не знайдено", show_alert=True)
                return
            _, topics = await topics_for_chat(db, chat_id)
        await callback.answer("Відновлено" if topic.is_active else "Поставлено на паузу")
        if callback.message:
            lines = "\n".join(topic_line(t) for t in topics)
            await callback.message.edit_text(f"Ваші теми:\n{lines}", reply_markup=keyboard(topics))

    @router.message()
    async def fallback(message: Message) -> None:
        await message.answer("Я розумію команди /topics, /pause, /resume і /start.")

    return router


async def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is empty: bot is idle (fake mode)")
        await asyncio.Event().wait()  # keep the container alive without polling
        return

    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(get_sessionmaker()))
    me = await bot.get_me()
    if me.username and me.username.lower() != settings.telegram_bot_username.lstrip("@").lower():
        logger.warning(
            "TELEGRAM_BOT_USERNAME=%s but the token belongs to @%s: deep links will be wrong",
            settings.telegram_bot_username,
            me.username,
        )
    if me.username:
        await get_redis().set(BOT_USERNAME_KEY, me.username)
    logger.info("bot @%s started (long polling)", me.username)
    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
