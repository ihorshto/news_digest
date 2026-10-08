from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.models import TelegramLinkToken, Topic, User
from app.services.telegram_link import (
    BOT_USERNAME_KEY,
    LinkResult,
    link_chat,
    set_topic_active,
    topics_for_chat,
)
from tests.conftest import register


async def _link_token(client) -> str:
    resp = await client.post("/api/telegram/link")
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == f"https://t.me/NewsDigestBot?start={body['token']}"
    return body["token"]


async def test_link_flow(client, sessionmaker):
    await register(client)
    token = await _link_token(client)

    async with sessionmaker() as db:
        result, user = await link_chat(db, token, chat_id=555, username="alice")
    assert result == LinkResult.linked

    me = (await client.get("/api/auth/me")).json()
    assert me["telegram_linked"] is True
    assert me["telegram_username"] == "alice"

    # Tokens are single-use.
    async with sessionmaker() as db:
        again, _ = await link_chat(db, token, chat_id=556, username="mallory")
    assert again == LinkResult.invalid

    assert (await client.post("/api/telegram/unlink")).status_code == 204
    assert (await client.get("/api/auth/me")).json()["telegram_linked"] is False


async def test_link_uses_live_bot_username(client, redis):
    await register(client)
    await redis.set(BOT_USERNAME_KEY, "RealDigestBot")
    body = (await client.post("/api/telegram/link")).json()
    assert body["url"].startswith("https://t.me/RealDigestBot?start=")


async def test_expired_and_unknown_tokens(client, sessionmaker):
    await register(client)
    token = await _link_token(client)
    async with sessionmaker() as db:
        row = await db.get(TelegramLinkToken, token)
        row.expires_at = utcnow() - timedelta(minutes=1)
        await db.commit()
        assert (await link_chat(db, token, 1, None))[0] == LinkResult.expired
        assert (await link_chat(db, "nope", 1, None))[0] == LinkResult.invalid


async def test_chat_moves_to_the_newest_account(client, sessionmaker):
    from tests.conftest import make_client

    await register(client, "first@example.com")
    first_token = await _link_token(client)
    other = await make_client()
    try:
        await register(other, "second@example.com")
        second_token = await _link_token(other)
    finally:
        await other.aclose()

    async with sessionmaker() as db:
        await link_chat(db, first_token, 777, None)
        await link_chat(db, second_token, 777, None)
        users = (await db.scalars(select(User).order_by(User.id))).all()
        assert [u.telegram_chat_id for u in users] == [None, 777]


async def test_relink_clears_blocked_flag(client, sessionmaker):
    await register(client)
    async with sessionmaker() as db:
        user = await db.scalar(select(User))
        user.telegram_blocked_at = utcnow()
        await db.commit()
    assert (await client.get("/api/auth/me")).json()["telegram_blocked"] is True
    token = await _link_token(client)
    async with sessionmaker() as db:
        await link_chat(db, token, 1, None)
    assert (await client.get("/api/auth/me")).json()["telegram_blocked"] is False


async def test_bot_pause_resume_only_own_topics(client, sessionmaker):
    await register(client)
    topic = (
        await client.post(
            "/api/topics",
            json={"name": "AI", "description": "AI models and regulation", "language": "en"},
        )
    ).json()
    token = await _link_token(client)
    async with sessionmaker() as db:
        await link_chat(db, token, 900, None)

        user, topics = await topics_for_chat(db, 900)
        assert user is not None and [t.id for t in topics] == [topic["id"]]
        assert (await topics_for_chat(db, 901))[0] is None

        # Another chat cannot touch this topic.
        assert await set_topic_active(db, 901, topic["id"], False) is None

        paused = await set_topic_active(db, 900, topic["id"], False)
        assert paused.is_active is False
        resumed = await set_topic_active(db, 900, topic["id"], True)
        assert resumed.is_active is True
        assert resumed.next_run_at is not None

    async with sessionmaker() as db:
        assert (await db.get(Topic, topic["id"])).is_active is True


def test_bot_keyboard_and_lines():
    from app.bot.main import keyboard, topic_line

    active = Topic(id=1, name="AI <news>", frequency="daily", is_active=True)
    paused = Topic(id=2, name="Crypto", frequency="6h", is_active=False)
    assert "AI &lt;news&gt;" in topic_line(active)
    markup = keyboard([active, paused])
    data = [row[0].callback_data for row in markup.inline_keyboard]
    assert data == ["t:pause:1", "t:resume:2"]
    assert keyboard([active, paused], only=False).inline_keyboard[0][0].callback_data == (
        "t:resume:2"
    )
    assert keyboard([paused], only=True) is None


async def test_bot_handlers_end_to_end(client, sessionmaker):
    """Feed real Telegram updates through the aiogram dispatcher (mocked Bot API session)."""
    from aiogram import Bot, Dispatcher
    from aiogram.client.session.base import BaseSession
    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
    from aiogram.types import Update

    from app.bot.main import build_router

    sent = []

    class RecordingSession(BaseSession):
        async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 (aiogram API)
            sent.append(method)
            if isinstance(method, SendMessage | EditMessageText):
                from aiogram.types import Chat, Message

                return Message(
                    message_id=1,
                    date=0,
                    chat=Chat(id=method.chat_id or 1, type="private"),
                    text=method.text,
                )
            if isinstance(method, AnswerCallbackQuery):
                return True
            raise AssertionError(f"unexpected method {method}")

        async def close(self):
            pass

        async def stream_content(self, *args, **kwargs):  # pragma: no cover
            raise NotImplementedError

    bot = Bot("123:abc", session=RecordingSession())
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(sessionmaker))

    def message_update(update_id: int, text: str) -> Update:
        return Update.model_validate(
            {
                "update_id": update_id,
                "message": {
                    "message_id": update_id,
                    "date": 0,
                    "chat": {"id": 4242, "type": "private"},
                    "from": {"id": 4242, "is_bot": False, "first_name": "A", "username": "al"},
                    "text": text,
                    "entities": [
                        {"type": "bot_command", "offset": 0, "length": len(text.split()[0])}
                    ],
                },
            },
            context={"bot": bot},
        )

    await register(client)
    await client.post(
        "/api/topics", json={"name": "AI", "description": "AI models", "language": "en"}
    )
    token = await _link_token(client)

    await dispatcher.feed_update(bot, message_update(1, f"/start {token}"))
    assert "Готово" in sent[-1].text
    assert (await client.get("/api/auth/me")).json()["telegram_username"] == "al"

    await dispatcher.feed_update(bot, message_update(2, "/start"))
    assert "NewsDigest" in sent[-1].text

    await dispatcher.feed_update(bot, message_update(3, "/topics"))
    reply = sent[-1]
    assert "AI" in reply.text
    callback_data = reply.reply_markup.inline_keyboard[0][0].callback_data
    assert callback_data.startswith("t:pause:")

    callback = Update.model_validate(
        {
            "update_id": 4,
            "callback_query": {
                "id": "cb1",
                "chat_instance": "x",
                "from": {"id": 4242, "is_bot": False, "first_name": "A"},
                "data": callback_data,
                "message": {
                    "message_id": 3,
                    "date": 0,
                    "chat": {"id": 4242, "type": "private"},
                    "text": "Ваші теми",
                },
            },
        },
        context={"bot": bot},
    )
    await dispatcher.feed_update(bot, callback)
    assert any(isinstance(m, AnswerCallbackQuery) for m in sent)
    assert isinstance(sent[-1], EditMessageText) and "на паузі" in sent[-1].text
    topics = (await client.get("/api/topics")).json()
    assert topics[0]["is_active"] is False
