from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.models import Digest, Topic, TopicArticle, TopicQuery, User
from app.services import pipeline as pipeline_module
from app.services.collectors.base import RawArticle
from app.services.digest_render import RenderItem, RenderLink, render_telegram_blocks
from app.services.embeddings import HashEmbedder
from app.services.llm import FakeLLMClient, LLMError
from app.services.pipeline import PipelineDeps, process_topic
from app.services.telegram import BotBlockedError, FakeTelegramSender, split_message

NOW = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)


class StubTavily:
    def __init__(self, articles=None):
        self.articles = articles or []
        self.calls = 0

    async def search(self, query, window, max_results):
        self.calls += 1
        return list(self.articles)


class BrokenLLM(FakeLLMClient):
    async def write_digest(self, *args, **kwargs):
        raise LLMError("model not found")


class BlockingTelegram(FakeTelegramSender):
    async def send_html(self, chat_id, text):
        raise BotBlockedError("Forbidden: bot was blocked by the user")


def art(title, url, hours_ago=1, snippet=None):
    return RawArticle(
        url=url,
        title=title,
        source_name="Example",
        published_at=NOW - timedelta(hours=hours_ago),
        snippet=snippet,
        origin="tavily",
    )


CRYPTO = [
    art("Bitcoin price climbs to record high", "https://a.com/1?utm_source=x"),
    art("Bitcoin price climbs to a record high today", "https://b.com/1"),  # same event
    art("Crypto exchange hack drains hot wallet", "https://c.com/2"),
    art("Pumpkin soup recipe for cold autumn evenings", "https://d.com/3"),  # irrelevant
    art("Bitcoin price record from last month", "https://e.com/old", hours_ago=72),  # stale
]


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(pipeline_module, "utcnow", lambda: NOW)


@pytest.fixture
def http():
    # Google News queries are not used in these tests (all queries are Tavily).
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))


def make_deps(sessionmaker, http, *, tavily=None, telegram=None, llm=None, **settings):
    base = {"database_url": "sqlite+aiosqlite://", "cluster_threshold": 0.8}
    return PipelineDeps(
        sessionmaker=sessionmaker,
        settings=Settings(**{**base, **settings}),
        llm=llm or FakeLLMClient(),
        embedder=HashEmbedder(),
        tavily=tavily or StubTavily(CRYPTO),
        telegram=telegram or FakeTelegramSender(),
        http=http,
    )


async def make_topic(db, chat_id=None, **kwargs) -> Topic:
    user = User(email=f"u{datetime.now().timestamp()}@x.com", password_hash="x")
    user.telegram_chat_id = chat_id
    db.add(user)
    await db.flush()
    topic = Topic(
        user_id=user.id,
        name="Crypto",
        description="Bitcoin price and crypto exchange hack news",
        language="en",
        frequency="daily",
        send_hour=9,
        weekday=0,
        relevance_threshold=0.3,
        next_run_at=NOW - timedelta(minutes=5),
        queries=[
            TopicQuery(query="bitcoin price", source="tavily", language="en"),
            TopicQuery(query="crypto exchange hack", source="google_news", language="en"),
        ],
        **kwargs,
    )
    db.add(topic)
    await db.commit()
    return topic


async def reload(sessionmaker, model, pk):
    async with sessionmaker() as session:
        return await session.get(model, pk)


async def digest_count(db, topic_id):
    return await db.scalar(select(func.count(Digest.id)).where(Digest.topic_id == topic_id))


async def test_full_run_creates_digest_and_marks_sent(sessionmaker, db, http):
    topic = await make_topic(db)
    deps = make_deps(sessionmaker, http)
    result = await process_topic(deps, topic.id, "slot-1")
    assert result.status == "fake_sent"
    assert result.events == 2  # two bitcoin articles merged into one event + the hack

    digest = await db.scalar(select(Digest).where(Digest.topic_id == topic.id))
    assert digest.status == "fake_sent"
    assert digest.article_count == 3
    assert "https://a.com/1?utm_source=x" in digest.content_markdown
    assert "https://b.com/1" in digest.content_markdown
    assert "Pumpkin" not in digest.content_markdown
    assert "last month" not in digest.content_markdown

    statuses = dict(
        (
            await db.execute(
                select(TopicArticle.status, func.count()).group_by(TopicArticle.status)
            )
        ).all()
    )
    assert statuses == {"sent": 3, "filtered": 1}  # stale one dropped before storing

    refreshed = await reload(sessionmaker, Topic, topic.id)
    assert refreshed.last_run_at == NOW
    assert refreshed.next_run_at > NOW
    assert refreshed.last_run_status == "fake_sent"


async def test_second_run_without_new_articles_sends_nothing(sessionmaker, db, http):
    topic = await make_topic(db)
    deps = make_deps(sessionmaker, http, tavily_min_interval_minutes=0)
    assert (await process_topic(deps, topic.id, "slot-1", manual=True)).status == "fake_sent"
    result = await process_topic(deps, topic.id, "slot-2", manual=True)
    assert result.status == "empty"
    assert await digest_count(db, topic.id) == 1


async def test_same_event_from_new_source_is_not_resent(sessionmaker, db, http):
    topic = await make_topic(db)
    tavily = StubTavily(CRYPTO)
    deps = make_deps(sessionmaker, http, tavily=tavily, tavily_min_interval_minutes=0)
    await process_topic(deps, topic.id, "slot-1", manual=True)
    tavily.articles = [art("Bitcoin price climbs to record high", "https://new-outlet.com/x")]
    result = await process_topic(deps, topic.id, "slot-2", manual=True)
    assert result.status == "empty"


async def test_irrelevant_only_sends_nothing(sessionmaker, db, http):
    topic = await make_topic(db)
    deps = make_deps(sessionmaker, http, tavily=StubTavily([CRYPTO[3]]))
    result = await process_topic(deps, topic.id, "slot-1")
    assert result.status == "empty"
    assert await digest_count(db, topic.id) == 0
    refreshed = await reload(sessionmaker, Topic, topic.id)
    assert refreshed.next_run_at > NOW  # still rescheduled
    assert refreshed.last_run_status == "empty"


async def test_same_run_key_is_idempotent(sessionmaker, db, http):
    topic = await make_topic(db)
    deps = make_deps(sessionmaker, http)
    assert (await process_topic(deps, topic.id, "slot-1", manual=True)).status == "fake_sent"
    again = await process_topic(deps, topic.id, "slot-1", manual=True)
    assert again.status == "skipped"
    assert await digest_count(db, topic.id) == 1


async def test_scheduled_run_skips_when_not_due_or_paused(sessionmaker, db, http):
    future = await make_topic(db)
    future.next_run_at = NOW + timedelta(hours=2)
    paused = await make_topic(db, is_active=False)
    await db.commit()
    deps = make_deps(sessionmaker, http)
    assert (await process_topic(deps, future.id, "x")).details["reason"] == "not due"
    assert (await process_topic(deps, paused.id, "x")).details["reason"] == "paused"
    # Manual runs ignore the schedule and the pause.
    assert (await process_topic(deps, paused.id, "m", manual=True)).status == "fake_sent"


async def test_real_telegram_delivery(sessionmaker, db, http):
    topic = await make_topic(db, chat_id=4242)
    telegram = FakeTelegramSender()
    deps = make_deps(sessionmaker, http, telegram=telegram, telegram_bot_token="123:abc")
    result = await process_topic(deps, topic.id, "slot-1")
    assert result.status == "sent"
    assert len(telegram.sent) == 1
    chat_id, text = telegram.sent[0]
    assert chat_id == 4242
    assert text.startswith("<b>📰 Crypto</b>")
    assert '<a href="https://a.com/1?utm_source=x">Example</a>' in text


async def test_no_chat_linked(sessionmaker, db, http):
    topic = await make_topic(db)
    deps = make_deps(sessionmaker, http, telegram_bot_token="123:abc")
    assert (await process_topic(deps, topic.id, "slot-1")).status == "no_chat"


async def test_bot_blocked_unlinks_user(sessionmaker, db, http):
    topic = await make_topic(db, chat_id=4242)
    deps = make_deps(sessionmaker, http, telegram=BlockingTelegram(), telegram_bot_token="123:abc")
    result = await process_topic(deps, topic.id, "slot-1")
    assert result.status == "failed"
    user = await reload(sessionmaker, User, topic.user_id)
    assert user.telegram_chat_id is None
    assert user.telegram_blocked_at is not None
    digest = await db.scalar(select(Digest).where(Digest.topic_id == topic.id))
    assert "bot_blocked" in digest.error
    # Articles stay candidates, so they can be delivered after re-linking.
    sent = await db.scalar(
        select(func.count()).select_from(TopicArticle).where(TopicArticle.status == "sent")
    )
    assert sent == 0


async def test_llm_failure_falls_back_to_extractive_digest(sessionmaker, db, http):
    topic = await make_topic(db)
    deps = make_deps(sessionmaker, http, llm=BrokenLLM())
    result = await process_topic(deps, topic.id, "slot-1")
    assert result.status == "fake_sent"
    digest = await db.scalar(select(Digest).where(Digest.topic_id == topic.id))
    assert "extractive fallback" in digest.error
    assert "Bitcoin price climbs" in digest.content_markdown


async def test_tavily_called_at_most_hourly(sessionmaker, db, http):
    topic = await make_topic(db)
    tavily = StubTavily(CRYPTO)
    deps = make_deps(sessionmaker, http, tavily=tavily)
    await process_topic(deps, topic.id, "slot-1", manual=True)
    await process_topic(deps, topic.id, "slot-2", manual=True)
    assert tavily.calls == 1


async def test_articles_are_shared_between_topics(sessionmaker, db, http):
    first = await make_topic(db)
    second = await make_topic(db)
    deps = make_deps(sessionmaker, http)
    await process_topic(deps, first.id, "a")
    await process_topic(deps, second.id, "a")
    from app.models import Article

    assert await db.scalar(select(func.count(Article.id))) == 5 - 1  # stale one never stored
    assert await digest_count(db, second.id) == 1


def test_split_message_respects_limit_and_blocks():
    blocks = ["<b>header</b>"] + [f"<b>{i}</b>\n" + "x" * 900 for i in range(10)]
    messages = split_message(blocks, limit=4096)
    assert len(messages) > 1
    assert all(len(m) <= 4096 for m in messages)
    assert "".join(messages).count("<b>") == 11
    assert all(m.count("<b>") == m.count("</b>") for m in messages)


def test_telegram_html_is_escaped():
    blocks = render_telegram_blocks(
        "A & B <script>",
        "08.10.2026",
        [
            RenderItem(
                title="Price < $5 & rising",
                summary='He said "hi" <b>',
                links=[
                    RenderLink("Src", 'https://x.com/?a=1&b="2"'),
                    RenderLink("Bad", "javascript:alert(1)"),
                ],
            )
        ],
    )
    text = "\n\n".join(blocks)
    assert "A &amp; B &lt;script&gt;" in text
    assert "Price &lt; $5 &amp; rising" in text
    assert "&lt;b&gt;" in text
    assert 'href="https://x.com/?a=1&amp;b=&quot;2&quot;"' in text
    assert "javascript" not in text
