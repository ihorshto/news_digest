from datetime import UTC, datetime, timedelta

import pytest

from app.models import Topic, User
from app.services.schedule import compute_next_run, freshness_window
from app.worker.main import enqueue_due_topics, slot_run_key
from tests.conftest import FakeQueue


def utc(*args):
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("frequency", "send_hour", "weekday", "tz", "after", "expected"),
    [
        # hourly: next full hour
        ("hourly", 8, 0, "Europe/Paris", utc(2026, 10, 8, 7, 12), utc(2026, 10, 8, 8, 0)),
        ("hourly", 8, 0, "Europe/Paris", utc(2026, 10, 8, 7, 0), utc(2026, 10, 8, 8, 0)),
        # half-hour offset zone: local full hours are :30 in UTC
        ("hourly", 8, 0, "Asia/Kolkata", utc(2026, 10, 8, 7, 12), utc(2026, 10, 8, 7, 30)),
        # 6h aligned to send_hour (9 -> 3, 9, 15, 21 local). Paris is UTC+2 in October.
        ("6h", 9, 0, "Europe/Paris", utc(2026, 10, 8, 7, 30), utc(2026, 10, 8, 13, 0)),
        ("6h", 9, 0, "Europe/Paris", utc(2026, 10, 8, 6, 59), utc(2026, 10, 8, 7, 0)),
        # daily at 09:00 Paris (UTC+2 in summer time)
        ("daily", 9, 0, "Europe/Paris", utc(2026, 10, 8, 6, 0), utc(2026, 10, 8, 7, 0)),
        ("daily", 9, 0, "Europe/Paris", utc(2026, 10, 8, 7, 0), utc(2026, 10, 9, 7, 0)),
        # daily across the DST change (Paris switches to UTC+1 on 2026-10-25)
        ("daily", 9, 0, "Europe/Paris", utc(2026, 10, 24, 8, 0), utc(2026, 10, 25, 8, 0)),
        # daily in New York (UTC-4 in October)
        ("daily", 7, 0, "America/New_York", utc(2026, 10, 8, 12, 0), utc(2026, 10, 9, 11, 0)),
        # local date differs from UTC date: 08:00 Tokyo is 23:00 UTC previous day
        ("daily", 8, 0, "Asia/Tokyo", utc(2026, 10, 8, 0, 0), utc(2026, 10, 8, 23, 0)),
        # weekly: Monday (0) 08:00 Kyiv (UTC+3); 2026-10-08 is a Thursday
        ("weekly", 8, 0, "Europe/Kyiv", utc(2026, 10, 8, 12, 0), utc(2026, 10, 12, 5, 0)),
        # weekly on the same weekday but after the hour -> next week
        ("weekly", 8, 3, "Europe/Kyiv", utc(2026, 10, 8, 6, 0), utc(2026, 10, 15, 5, 0)),
        ("weekly", 8, 3, "Europe/Kyiv", utc(2026, 10, 8, 4, 0), utc(2026, 10, 8, 5, 0)),
    ],
)
def test_compute_next_run(frequency, send_hour, weekday, tz, after, expected):
    result = compute_next_run(frequency, send_hour, weekday, tz, after)
    assert result == expected
    assert result.tzinfo is not None


def test_next_run_is_strictly_after_and_progresses():
    now = utc(2026, 3, 28, 22, 30)  # around the spring DST switch in Europe
    for freq in ("hourly", "6h", "daily", "weekly"):
        current = now
        for _ in range(30):
            nxt = compute_next_run(freq, 9, 6, "Europe/Paris", current)
            assert nxt > current
            assert nxt - current <= timedelta(days=7, hours=1)
            current = nxt


def test_freshness_window():
    assert freshness_window("hourly") == timedelta(hours=1)
    assert freshness_window("weekly") == timedelta(days=7)


def test_slot_run_key_is_stable():
    assert slot_run_key(utc(2026, 10, 8, 7, 0)) == "slot-20261008T0700"


async def _topic(db, **kwargs):
    user = User(email=f"{id(kwargs)}@x.com", password_hash="x", timezone="Europe/Paris")
    db.add(user)
    await db.flush()
    topic = Topic(
        user_id=user.id,
        name="t",
        description="d",
        relevance_threshold=0.3,
        frequency="daily",
        send_hour=9,
        **kwargs,
    )
    db.add(topic)
    await db.commit()
    return topic


async def test_tick_enqueues_due_topics_once(sessionmaker, db):
    now = utc(2026, 10, 8, 7, 2)
    due = await _topic(db, next_run_at=utc(2026, 10, 8, 7, 0))
    await _topic(db, next_run_at=utc(2026, 10, 9, 7, 0))  # not due
    await _topic(db, next_run_at=utc(2026, 10, 8, 7, 0), is_active=False)  # paused
    unscheduled = await _topic(db, next_run_at=None)

    queue = FakeQueue()
    assert await enqueue_due_topics(sessionmaker, queue, now) == 1
    assert list(queue.jobs) == [f"topic:{due.id}:slot-20261008T0700"]
    # A second tick before the job ran does not enqueue a duplicate.
    assert await enqueue_due_topics(sessionmaker, queue, now) == 0
    assert len(queue.jobs) == 1

    async with sessionmaker() as session:
        refreshed = await session.get(Topic, unscheduled.id)
        assert refreshed.next_run_at == utc(2026, 10, 9, 7, 0)


async def test_job_retries_when_topic_locked(redis):
    from arq import Retry

    from app.worker.main import process_topic_job

    await redis.set("lock:topic:7", "someone-else", ex=60)
    with pytest.raises(Retry):
        await process_topic_job({"redis": redis}, 7, "slot-x", False)
    assert await redis.get("lock:topic:7") == "someone-else"  # not released by us
