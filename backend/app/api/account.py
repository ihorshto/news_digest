from fastapi import APIRouter

from app.api.auth import user_out
from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.api.schemas import MetaOut, UserOut, UserUpdateIn
from app.models import Frequency
from app.services.languages import SUPPORTED_LANGUAGES
from app.services.topics import reschedule_user_topics

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta", response_model=MetaOut)
async def meta(settings: SettingsDep) -> MetaOut:
    return MetaOut(
        bot_username=settings.telegram_bot_username,
        languages=SUPPORTED_LANGUAGES,
        frequencies=[f.value for f in Frequency],
        max_topics_per_user=settings.max_topics_per_user,
        default_relevance_threshold=settings.relevance_threshold,
        fake_llm=settings.fake_llm,
        fake_tavily=settings.fake_tavily,
        fake_telegram=settings.fake_telegram,
    )


@router.patch("/me", response_model=UserOut)
async def update_me(payload: UserUpdateIn, user: CurrentUser, db: DbSession) -> UserOut:
    user.timezone = payload.timezone
    await db.commit()
    # Schedules are wall-clock based, so a timezone change moves every slot.
    await reschedule_user_topics(db, user)
    return user_out(user)
