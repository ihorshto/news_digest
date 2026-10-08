from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import Topic, User
from app.services.schedule import compute_next_run


def reschedule(topic: Topic, timezone: str) -> None:
    topic.next_run_at = compute_next_run(
        topic.frequency, topic.send_hour, topic.weekday, timezone, utcnow()
    )


async def reschedule_user_topics(db: AsyncSession, user: User) -> None:
    topics = (await db.scalars(select(Topic).where(Topic.user_id == user.id))).all()
    for topic in topics:
        reschedule(topic, user.timezone)
    await db.commit()
