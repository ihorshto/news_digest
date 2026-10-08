from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, RedisDep, SettingsDep
from app.api.schemas import TelegramLinkOut
from app.services.telegram_link import BOT_USERNAME_KEY, create_link_token

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/link", response_model=TelegramLinkOut)
async def create_link(
    user: CurrentUser, db: DbSession, settings: SettingsDep, redis: RedisDep
) -> TelegramLinkOut:
    token = await create_link_token(db, user, settings.telegram_link_ttl_minutes)
    # The running bot publishes its real username; fall back to the configured one.
    username = (await redis.get(BOT_USERNAME_KEY)) or settings.telegram_bot_username.lstrip("@")
    return TelegramLinkOut(
        url=f"https://t.me/{username}?start={token.token}",
        token=token.token,
        expires_at=token.expires_at,
    )


@router.post("/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(user: CurrentUser, db: DbSession) -> None:
    user.telegram_chat_id = None
    user.telegram_username = None
    user.telegram_blocked_at = None
    await db.commit()
