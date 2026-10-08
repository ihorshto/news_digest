"""Account linking and bot-side topic management (shared by API and bot)."""

from datetime import timedelta
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import new_token
from app.db.base import utcnow
from app.models import TelegramLinkToken, Topic, User
from app.services.topics import reschedule

BOT_USERNAME_KEY = "telegram:bot_username"


class LinkResult(StrEnum):
    linked = "linked"
    invalid = "invalid"
    expired = "expired"


async def create_link_token(db: AsyncSession, user: User, ttl_minutes: int) -> TelegramLinkToken:
    token = TelegramLinkToken(
        token=new_token(24),  # url-safe, fits Telegram's 64-char start parameter
        user_id=user.id,
        expires_at=utcnow() + timedelta(minutes=ttl_minutes),
    )
    db.add(token)
    await db.commit()
    return token


async def link_chat(
    db: AsyncSession, token_value: str, chat_id: int, username: str | None
) -> tuple[LinkResult, User | None]:
    token = await db.get(TelegramLinkToken, token_value[:64])
    if token is None or token.used_at is not None:
        return LinkResult.invalid, None
    if token.expires_at < utcnow():
        return LinkResult.expired, None
    user = await db.get(User, token.user_id)
    if user is None:
        return LinkResult.invalid, None
    # One chat belongs to one account: detach it from any other user first.
    await db.execute(
        update(User)
        .where(User.telegram_chat_id == chat_id, User.id != user.id)
        .values(telegram_chat_id=None, telegram_username=None)
    )
    token.used_at = utcnow()
    user.telegram_chat_id = chat_id
    user.telegram_username = username
    user.telegram_blocked_at = None
    await db.commit()
    return LinkResult.linked, user


async def user_by_chat(db: AsyncSession, chat_id: int) -> User | None:
    return await db.scalar(select(User).where(User.telegram_chat_id == chat_id))


async def topics_for_chat(db: AsyncSession, chat_id: int) -> tuple[User | None, list[Topic]]:
    user = await user_by_chat(db, chat_id)
    if user is None:
        return None, []
    topics = (
        await db.scalars(select(Topic).where(Topic.user_id == user.id).order_by(Topic.id))
    ).all()
    return user, list(topics)


async def set_topic_active(
    db: AsyncSession, chat_id: int, topic_id: int, active: bool
) -> Topic | None:
    """Pause/resume a topic, but only if it belongs to the account linked to this chat."""
    topic = await db.scalar(
        select(Topic)
        .join(User, User.id == Topic.user_id)
        .where(Topic.id == topic_id, User.telegram_chat_id == chat_id)
        .options(selectinload(Topic.user))
    )
    if topic is None:
        return None
    topic.is_active = active
    if active:
        reschedule(topic, topic.user.timezone)
    await db.commit()
    return topic
