from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import Frequency, QuerySource
from app.services.languages import SUPPORTED_LANGUAGES

_TIMEZONES = available_timezones()


def _validate_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("invalid_timezone")
    return value


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return _validate_timezone(value) if value else None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    timezone: str
    telegram_linked: bool
    telegram_username: str | None
    telegram_blocked: bool
    created_at: datetime


class UserUpdateIn(BaseModel):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return _validate_timezone(value)


class TopicQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    source: QuerySource = QuerySource.google_news
    language: str = "en"

    @field_validator("query")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty_query")
        return value

    @field_validator("language")
    @classmethod
    def _lang(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError("unsupported_language")
        return value


class TopicQueryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    source: str
    language: str


class TopicBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    language: str = "uk"
    frequency: Frequency = Frequency.daily
    send_hour: int = Field(default=8, ge=0, le=23)
    weekday: int = Field(default=0, ge=0, le=6)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("language")
    @classmethod
    def _lang(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError("unsupported_language")
        return value


class TopicCreateIn(TopicBase):
    relevance_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class TopicUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    language: str | None = None
    frequency: Frequency | None = None
    send_hour: int | None = Field(default=None, ge=0, le=23)
    weekday: int | None = Field(default=None, ge=0, le=6)
    is_active: bool | None = None
    relevance_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("language")
    @classmethod
    def _lang(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_LANGUAGES:
            raise ValueError("unsupported_language")
        return value

    @model_validator(mode="after")
    def _strip(self) -> "TopicUpdateIn":
        if self.name is not None:
            self.name = self.name.strip()
        if self.description is not None:
            self.description = self.description.strip()
        return self


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    language: str
    frequency: str
    send_hour: int
    weekday: int
    is_active: bool
    relevance_threshold: float
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_run_status: str | None
    created_at: datetime
    queries: list[TopicQueryOut] = []
    digest_count: int = 0


class DigestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    created_at: datetime
    sent_at: datetime | None
    status: str
    content_markdown: str
    article_count: int
    error: str | None


class RunOut(BaseModel):
    job_id: str
    enqueued: bool


class TelegramLinkOut(BaseModel):
    url: str
    token: str
    expires_at: datetime


class MetaOut(BaseModel):
    bot_username: str
    languages: dict[str, str]
    frequencies: list[str]
    max_topics_per_user: int
    default_relevance_threshold: float
    fake_llm: bool
    fake_tavily: bool
    fake_telegram: bool
