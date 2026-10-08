from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.api.schemas import (
    DigestOut,
    RunOut,
    TopicCreateIn,
    TopicOut,
    TopicQueryIn,
    TopicUpdateIn,
)
from app.core.config import Settings, get_settings
from app.core.queue import JobQueue, enqueue_topic_run, get_queue
from app.db.base import utcnow
from app.models import Digest, Topic, User
from app.services.llm import GeneratedQuery, LLMClient, get_llm_client
from app.services.topics import generate_queries, reschedule, set_queries

router = APIRouter(prefix="/api/topics", tags=["topics"])

MAX_QUERIES_PER_TOPIC = 20


def llm_dependency(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    return get_llm_client(settings)


LLMDep = Annotated[LLMClient, Depends(llm_dependency)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]


async def get_owned_topic(db: DbSession, user: User, topic_id: int) -> Topic:
    topic = await db.scalar(
        select(Topic)
        .where(Topic.id == topic_id, Topic.user_id == user.id)
        .options(selectinload(Topic.queries))
    )
    if topic is None:
        # 404 (not 403) so other users' topic ids are not revealed.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return topic


async def _digest_counts(db: DbSession, topic_ids: list[int]) -> dict[int, int]:
    if not topic_ids:
        return {}
    rows = await db.execute(
        select(Digest.topic_id, func.count(Digest.id))
        .where(Digest.topic_id.in_(topic_ids))
        .group_by(Digest.topic_id)
    )
    return {topic_id: count for topic_id, count in rows.all()}


async def _topic_out(db: DbSession, topic: Topic) -> TopicOut:
    out = TopicOut.model_validate(topic)
    out.digest_count = (await _digest_counts(db, [topic.id])).get(topic.id, 0)
    return out


@router.get("", response_model=list[TopicOut])
async def list_topics(user: CurrentUser, db: DbSession) -> list[TopicOut]:
    topics = (
        await db.scalars(
            select(Topic)
            .where(Topic.user_id == user.id)
            .options(selectinload(Topic.queries))
            .order_by(Topic.created_at.desc(), Topic.id.desc())
        )
    ).all()
    counts = await _digest_counts(db, [t.id for t in topics])
    result = []
    for topic in topics:
        out = TopicOut.model_validate(topic)
        out.digest_count = counts.get(topic.id, 0)
        result.append(out)
    return result


@router.post("", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
async def create_topic(
    payload: TopicCreateIn, user: CurrentUser, db: DbSession, settings: SettingsDep, llm: LLMDep
) -> TopicOut:
    count = await db.scalar(select(func.count(Topic.id)).where(Topic.user_id == user.id))
    if (count or 0) >= settings.max_topics_per_user:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="topic_limit_reached")

    topic = Topic(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        language=payload.language,
        frequency=payload.frequency.value,
        send_hour=payload.send_hour,
        weekday=payload.weekday,
        is_active=True,
        relevance_threshold=payload.relevance_threshold or settings.relevance_threshold,
        queries=[],
    )
    reschedule(topic, user.timezone)
    await generate_queries(llm, topic)
    db.add(topic)
    await db.commit()
    return await _topic_out(db, await get_owned_topic(db, user, topic.id))


@router.get("/{topic_id}", response_model=TopicOut)
async def get_topic(topic_id: int, user: CurrentUser, db: DbSession) -> TopicOut:
    return await _topic_out(db, await get_owned_topic(db, user, topic_id))


@router.patch("/{topic_id}", response_model=TopicOut)
async def update_topic(
    topic_id: int, payload: TopicUpdateIn, user: CurrentUser, db: DbSession, llm: LLMDep
) -> TopicOut:
    topic = await get_owned_topic(db, user, topic_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)

    regenerate = any(
        key in changes and changes[key] != getattr(topic, key)
        for key in ("description", "language")
    )
    schedule_keys = ("frequency", "send_hour", "weekday", "is_active")
    resched = any(key in changes and changes[key] != getattr(topic, key) for key in schedule_keys)

    for key, value in changes.items():
        setattr(topic, key, value.value if hasattr(value, "value") else value)

    if regenerate:
        await generate_queries(llm, topic)
    if resched and topic.is_active:
        reschedule(topic, user.timezone)
    await db.commit()
    return await _topic_out(db, await get_owned_topic(db, user, topic_id))


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: int, user: CurrentUser, db: DbSession) -> None:
    topic = await get_owned_topic(db, user, topic_id)
    await db.delete(topic)
    await db.commit()


@router.put("/{topic_id}/queries", response_model=TopicOut)
async def replace_queries(
    topic_id: int, payload: list[TopicQueryIn], user: CurrentUser, db: DbSession
) -> TopicOut:
    if len(payload) > MAX_QUERIES_PER_TOPIC:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="too_many_queries")
    topic = await get_owned_topic(db, user, topic_id)
    set_queries(topic, [GeneratedQuery(q.query, q.source.value, q.language) for q in payload])
    await db.commit()
    return await _topic_out(db, await get_owned_topic(db, user, topic_id))


@router.post("/{topic_id}/queries/regenerate", response_model=TopicOut)
async def regenerate_queries(
    topic_id: int, user: CurrentUser, db: DbSession, llm: LLMDep
) -> TopicOut:
    topic = await get_owned_topic(db, user, topic_id)
    await generate_queries(llm, topic)
    await db.commit()
    return await _topic_out(db, await get_owned_topic(db, user, topic_id))


@router.post("/{topic_id}/run", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def run_topic(topic_id: int, user: CurrentUser, db: DbSession, queue: QueueDep) -> RunOut:
    topic = await get_owned_topic(db, user, topic_id)
    # One manual run per topic per minute: repeated clicks map to the same job id.
    run_key = "manual-" + utcnow().strftime("%Y%m%d%H%M")
    enqueued = await enqueue_topic_run(queue, topic.id, run_key, manual=True)
    topic.last_run_status = "queued"
    await db.commit()
    return RunOut(job_id=f"topic:{topic.id}:{run_key}", enqueued=enqueued)


@router.get("/{topic_id}/digests", response_model=list[DigestOut])
async def list_digests(
    topic_id: int, user: CurrentUser, db: DbSession, limit: int = 50
) -> list[Digest]:
    await get_owned_topic(db, user, topic_id)
    rows = await db.scalars(
        select(Digest)
        .where(Digest.topic_id == topic_id)
        .order_by(Digest.created_at.desc(), Digest.id.desc())
        .limit(min(max(limit, 1), 200))
    )
    return list(rows.all())
