"""process_topic: collect -> dedupe -> embed -> filter -> cluster -> summarize -> deliver."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.base import utcnow
from app.models import (
    Article,
    Digest,
    DigestStatus,
    QuerySource,
    Topic,
    TopicArticle,
    TopicArticleStatus,
    User,
)
from app.services.collectors.base import RawArticle
from app.services.collectors.google_news import fetch_google_news
from app.services.collectors.tavily import TavilySearcher
from app.services.digest_render import (
    RenderItem,
    RenderLink,
    format_date,
    render_markdown,
    render_telegram_blocks,
)
from app.services.embeddings import Embedder, article_text, from_bytes, to_bytes
from app.services.llm import EventArticle, EventInput, FakeLLMClient, LLMClient
from app.services.relevance import cluster_events, profile_texts, relevance_scores
from app.services.schedule import GOOGLE_WHEN, compute_next_run, freshness_window
from app.services.telegram import BotBlockedError, TelegramError, TelegramSender, split_message
from app.services.urls import url_hash

logger = logging.getLogger(__name__)

FRESHNESS_SLACK = timedelta(minutes=30)
SENT_LOOKBACK = timedelta(days=3)
MAX_LINKS_PER_EVENT = 3
DELIVERED = {DigestStatus.sent, DigestStatus.fake_sent, DigestStatus.no_chat}


@dataclass
class PipelineDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: Settings
    llm: LLMClient
    embedder: Embedder
    tavily: TavilySearcher
    telegram: TelegramSender
    http: httpx.AsyncClient


@dataclass
class RunResult:
    status: str  # skipped | empty | sent | fake_sent | no_chat | failed
    digest_id: int | None = None
    events: int = 0
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------- collection


async def collect(deps: PipelineDeps, topic: Topic, now: datetime) -> list[RawArticle]:
    settings = deps.settings
    window = freshness_window(topic.frequency)
    when = GOOGLE_WHEN.get(topic.frequency, "1d")
    semaphore = asyncio.Semaphore(4)

    async def google(query: str, language: str) -> list[RawArticle]:
        async with semaphore:
            return await fetch_google_news(
                deps.http, query, language, when, settings.google_news_max_items_per_query
            )

    google_queries = [q for q in topic.queries if q.source == QuerySource.google_news]
    tasks = [google(q.query, q.language) for q in google_queries]

    tavily_queries = [q for q in topic.queries if q.source == QuerySource.tavily]
    tavily_due = topic.last_tavily_at is None or now - topic.last_tavily_at >= timedelta(
        minutes=settings.tavily_min_interval_minutes
    )
    if tavily_queries and tavily_due:
        topic.last_tavily_at = now
        tasks += [
            deps.tavily.search(q.query, window, settings.tavily_max_results) for q in tavily_queries
        ]
    elif tavily_queries:
        logger.info("topic %s: Tavily skipped (called less than an hour ago)", topic.id)

    results = await asyncio.gather(*tasks)
    raw = [article for batch in results for article in batch]

    cutoff = now - window - FRESHNESS_SLACK
    fresh: dict[str, RawArticle] = {}
    for article in raw:
        if article.published_at is not None and article.published_at < cutoff:
            continue
        if article.published_at is not None and article.published_at > now + timedelta(hours=1):
            continue  # clock skew / bogus dates
        fresh.setdefault(url_hash(article.url), article)
    logger.info(
        "topic %s: collected %d raw, %d fresh unique (window %s)",
        topic.id,
        len(raw),
        len(fresh),
        window,
    )
    return list(fresh.values())


async def upsert_articles(db: AsyncSession, raw: list[RawArticle]) -> list[Article]:
    """Store new articles once (shared across topics) and return all of them.

    Uses INSERT IGNORE / ON CONFLICT DO NOTHING so concurrent jobs for different
    topics that found the same article do not fail on the unique url_hash.
    """
    by_hash = {url_hash(a.url): a for a in raw}
    if not by_hash:
        return []
    known = set(
        (
            await db.scalars(select(Article.url_hash).where(Article.url_hash.in_(list(by_hash))))
        ).all()
    )
    rows = [
        {
            "url_hash": h,
            "url": item.url,
            "title": item.title,
            "source_name": (item.source_name or "")[:255] or None,
            "published_at": item.published_at,
            "snippet": item.snippet,
            "fetched_at": utcnow(),
        }
        for h, item in by_hash.items()
        if h not in known
    ]
    if rows:
        dialect = db.bind.dialect.name
        if dialect == "mysql":
            stmt = mysql_insert(Article).prefix_with("IGNORE")
        elif dialect == "sqlite":
            stmt = sqlite_insert(Article).on_conflict_do_nothing(index_elements=["url_hash"])
        else:
            stmt = insert(Article)
        await db.execute(stmt, rows)
    return list(
        (await db.scalars(select(Article).where(Article.url_hash.in_(list(by_hash))))).all()
    )


async def ensure_embeddings(deps: PipelineDeps, articles: list[Article]) -> None:
    missing = [a for a in articles if a.embedding is None]
    if not missing:
        return
    texts = [article_text(a.title, a.snippet) for a in missing]
    vectors = await asyncio.to_thread(deps.embedder.embed, texts)
    for article, vector in zip(missing, vectors, strict=True):
        article.embedding = to_bytes(vector)


async def topic_profile(deps: PipelineDeps, topic: Topic) -> np.ndarray:
    texts = profile_texts(
        topic.description,
        [q.query for q in topic.queries if q.source == QuerySource.google_news],
    )
    digest = hashlib.sha256(
        (deps.settings.embedding_model + "\n" + "\n".join(texts)).encode()
    ).hexdigest()
    if topic.description_hash != digest or topic.description_embedding is None:
        vectors = await asyncio.to_thread(deps.embedder.embed, texts)
        topic.description_embedding = to_bytes(vectors)
        topic.description_hash = digest
        return vectors
    flat = from_bytes(topic.description_embedding)
    return flat.reshape(len(texts), -1)


# ---------------------------------------------------------------- selection


@dataclass
class Event:
    leader: TopicArticle
    members: list[TopicArticle]


async def score_new(
    db: AsyncSession, topic: Topic, articles: list[Article], profile: np.ndarray
) -> None:
    """Create topic_article rows for articles this topic has not seen yet."""
    if not articles:
        return
    seen = set(
        (
            await db.scalars(
                select(TopicArticle.article_id).where(
                    TopicArticle.topic_id == topic.id,
                    TopicArticle.article_id.in_([a.id for a in articles]),
                )
            )
        ).all()
    )
    new = [a for a in articles if a.id not in seen]
    if not new:
        return
    vectors = np.stack([from_bytes(a.embedding) for a in new])
    scores = relevance_scores(profile, vectors)
    passed = 0
    for article, score in zip(new, scores, strict=True):
        ok = float(score) >= topic.relevance_threshold
        passed += ok
        logger.debug(
            "topic %s score=%.3f %s %s",
            topic.id,
            score,
            "PASS" if ok else "drop",
            article.title[:120],
        )
        db.add(
            TopicArticle(
                topic_id=topic.id,
                article_id=article.id,
                relevance_score=float(score),
                status=(TopicArticleStatus.candidate if ok else TopicArticleStatus.filtered).value,
            )
        )
    if len(scores):
        logger.info(
            "topic %s: scored %d new articles, %d passed threshold %.2f "
            "(min %.3f / median %.3f / max %.3f)",
            topic.id,
            len(new),
            passed,
            topic.relevance_threshold,
            float(np.min(scores)),
            float(np.median(scores)),
            float(np.max(scores)),
        )
    await db.flush()


async def select_events(
    deps: PipelineDeps, db: AsyncSession, topic: Topic, now: datetime
) -> list[Event]:
    cutoff = now - freshness_window(topic.frequency) - FRESHNESS_SLACK
    candidates = (
        await db.scalars(
            select(TopicArticle)
            .where(
                TopicArticle.topic_id == topic.id,
                TopicArticle.status == TopicArticleStatus.candidate,
            )
            .options(selectinload(TopicArticle.article))
        )
    ).all()
    fresh = []
    for ta in candidates:
        published = ta.article.published_at or ta.article.fetched_at
        if published >= cutoff:
            fresh.append(ta)
        else:
            ta.status = TopicArticleStatus.filtered.value  # stale, never send later
    if not fresh:
        return []

    vectors = np.stack([from_bytes(ta.article.embedding) for ta in fresh])
    threshold = deps.settings.cluster_threshold

    # Drop events that were already sent for this topic recently.
    sent = (
        await db.scalars(
            select(TopicArticle)
            .where(
                TopicArticle.topic_id == topic.id,
                TopicArticle.status == TopicArticleStatus.sent,
                TopicArticle.created_at >= now - SENT_LOOKBACK,
            )
            .options(selectinload(TopicArticle.article))
        )
    ).all()
    keep = np.ones(len(fresh), dtype=bool)
    if sent:
        sent_vectors = np.stack([from_bytes(ta.article.embedding) for ta in sent])
        already = (vectors @ sent_vectors.T).max(axis=1) >= threshold
        for i in np.flatnonzero(already):
            fresh[i].status = TopicArticleStatus.filtered.value
            logger.info("topic %s: same event already sent: %s", topic.id, fresh[i].article.title)
        keep &= ~already
    indices = [i for i in np.flatnonzero(keep)]
    if not indices:
        return []

    order = sorted(indices, key=lambda i: -fresh[i].relevance_score)
    clusters = cluster_events(vectors, order, threshold)
    events = [Event(leader=fresh[c[0]], members=[fresh[i] for i in c]) for c in clusters]
    return events[: deps.settings.max_events_per_digest]


# ---------------------------------------------------------------- run


def _schedule_next(topic: Topic, user: User, now: datetime) -> None:
    topic.next_run_at = compute_next_run(
        topic.frequency, topic.send_hour, topic.weekday, user.timezone, now
    )


async def _write_items(deps: PipelineDeps, topic: Topic, events: list[Event]):
    inputs = [
        EventInput(
            event_id=index,
            articles=[
                EventArticle(
                    title=m.article.title,
                    url=m.article.url,
                    source_name=m.article.source_name,
                    snippet=m.article.snippet,
                    published_at=m.article.published_at,
                )
                for m in event.members[:MAX_LINKS_PER_EVENT]
            ],
        )
        for index, event in enumerate(events, start=1)
    ]
    try:
        items = await deps.llm.write_digest(topic.name, topic.description, topic.language, inputs)
        return items, None
    except Exception as exc:  # any provider failure falls back to an extractive digest
        logger.exception("topic %s: LLM digest failed, using extractive fallback", topic.id)
        items = await FakeLLMClient().write_digest(
            topic.name, topic.description, topic.language, inputs
        )
        return items, f"LLM error, extractive fallback used: {exc}"[:1000]


async def process_topic(
    deps: PipelineDeps, topic_id: int, run_key: str, manual: bool = False
) -> RunResult:
    now = utcnow()
    async with deps.sessionmaker() as db:
        topic = await db.scalar(
            select(Topic)
            .where(Topic.id == topic_id)
            .options(selectinload(Topic.queries), selectinload(Topic.user))
        )
        if topic is None:
            return RunResult("skipped", details={"reason": "topic not found"})
        user = topic.user
        if not manual:
            if not topic.is_active:
                return RunResult("skipped", details={"reason": "paused"})
            if topic.next_run_at and topic.next_run_at > now + timedelta(minutes=1):
                # Slot already processed (duplicate tick / retry after success).
                return RunResult("skipped", details={"reason": "not due"})

        full_run_key = f"{topic.id}:{run_key}"
        if await db.scalar(select(Digest.id).where(Digest.run_key == full_run_key)):
            return RunResult("skipped", details={"reason": "run already produced a digest"})

        raw = await collect(deps, topic, now)
        articles = await upsert_articles(db, raw)
        await ensure_embeddings(deps, articles)
        profile = await topic_profile(deps, topic)
        await db.flush()
        await score_new(db, topic, articles, profile)
        events = await select_events(deps, db, topic, now)

        topic.last_run_at = now
        if not manual:
            _schedule_next(topic, user, now)

        if not events:
            topic.last_run_status = "empty"
            await db.commit()
            logger.info("topic %s: no new relevant articles, nothing sent", topic.id)
            return RunResult("empty")

        items, llm_error = await _write_items(deps, topic, events)
        by_id = {index: event for index, event in enumerate(events, start=1)}
        render_items = []
        used_events = []
        for item in items:
            event = by_id[item.event_id]
            used_events.append(event)
            event.leader.article.summary = item.summary
            render_items.append(
                RenderItem(
                    title=item.title,
                    summary=item.summary,
                    links=[
                        RenderLink(m.article.source_name or "source", m.article.url)
                        for m in event.members[:MAX_LINKS_PER_EVENT]
                    ],
                )
            )
        when_label = format_date(now, user.timezone)
        markdown = render_markdown(topic.name, when_label, render_items)
        article_count = sum(len(e.members) for e in used_events)

        # Persist the digest *before* sending: the unique run_key makes a retried job
        # stop at the check above instead of sending the same digest twice.
        digest = Digest(
            topic_id=topic.id,
            status="pending",
            content_markdown=markdown,
            article_count=article_count,
            error=llm_error,
            run_key=full_run_key,
        )
        db.add(digest)
        for cluster_index, event in enumerate(used_events, start=1):
            for member in event.members:
                member.cluster_id = f"{full_run_key}:{cluster_index}"
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return RunResult("skipped", details={"reason": "concurrent run"})

        status, send_error = await deliver(deps, db, user, topic, when_label, render_items)
        digest.status = status.value
        if send_error:
            digest.error = f"{digest.error}; {send_error}" if digest.error else send_error
        if status in DELIVERED:
            digest.sent_at = utcnow()
            for event in used_events:
                for member in event.members:
                    member.status = TopicArticleStatus.sent.value
                    member.digest_id = digest.id
        topic.last_run_status = status.value
        await db.commit()
        logger.info(
            "topic %s: digest %s %s (%d events)", topic.id, digest.id, status, len(used_events)
        )
        return RunResult(status.value, digest_id=digest.id, events=len(used_events))


async def deliver(
    deps: PipelineDeps,
    db: AsyncSession,
    user: User,
    topic: Topic,
    when_label: str,
    items: list[RenderItem],
) -> tuple[DigestStatus, str | None]:
    if deps.settings.fake_telegram:
        return DigestStatus.fake_sent, None
    if user.telegram_chat_id is None:
        return DigestStatus.no_chat, None
    messages = split_message(render_telegram_blocks(topic.name, when_label, items))
    try:
        for message in messages:
            await deps.telegram.send_html(user.telegram_chat_id, message)
    except BotBlockedError as exc:
        logger.warning("user %s blocked the bot: %s", user.id, exc)
        user.telegram_chat_id = None
        user.telegram_blocked_at = utcnow()
        return DigestStatus.failed, f"bot_blocked: {exc}"
    except TelegramError as exc:
        return DigestStatus.failed, f"telegram: {exc}"
    return DigestStatus.sent, None
