from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, RedisDep, SettingsDep, client_ip
from app.api.schemas import LoginIn, RegisterIn, UserOut
from app.core.config import Settings
from app.core.redis import hit_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verifying against a dummy hash keeps login timing similar for unknown emails.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        timezone=user.timezone,
        telegram_linked=user.telegram_chat_id is not None,
        telegram_username=user.telegram_username,
        telegram_blocked=user.telegram_blocked_at is not None and user.telegram_chat_id is None,
        created_at=user.created_at,
    )


def _set_session(response: Response, user: User, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        create_access_token(user.id),
        max_age=settings.jwt_ttl_hours * 3600,
        httponly=True,
        secure=bool(settings.cookie_secure),
        samesite="lax",
        path="/",
    )


async def _check_rate_limit(redis, settings: Settings, scope: str, request: Request) -> None:
    key = f"{scope}:{client_ip(request)}"
    if await hit_rate_limit(redis, key, settings.rate_limit_auth_per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")


@router.get("/csrf")
async def csrf(request: Request) -> dict[str, str]:
    return {"csrf_token": request.state.csrf_token}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> UserOut:
    await _check_rate_limit(redis, settings, "register", request)
    email = payload.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email_taken")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        timezone=payload.timezone or settings.default_timezone,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email_taken") from exc
    await db.refresh(user)
    _set_session(response, user, settings)
    return user_out(user)


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> UserOut:
    await _check_rate_limit(redis, settings, "login", request)
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    _set_session(response, user, settings)
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: SettingsDep) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)
