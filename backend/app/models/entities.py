from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow

LongText = Text().with_variant(MEDIUMTEXT(), "mysql")


class Frequency(StrEnum):
    hourly = "hourly"
    six_hours = "6h"
    daily = "daily"
    weekly = "weekly"


class QuerySource(StrEnum):
    google_news = "google_news"
    tavily = "tavily"


class TopicArticleStatus(StrEnum):
    candidate = "candidate"
    sent = "sent"
    filtered = "filtered"


class DigestStatus(StrEnum):
    sent = "sent"  # delivered via Telegram
    fake_sent = "fake_sent"  # Telegram in fake mode: stored only
    no_chat = "no_chat"  # user has no linked Telegram chat
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris")
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Set when Telegram reports that the bot was blocked; cleared on re-link.
    telegram_blocked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    topics: Mapped[list["Topic"]] = relationship(back_populates="user", cascade="all, delete")


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="uk")
    frequency: Mapped[str] = mapped_column(String(16), default=Frequency.daily.value)
    send_hour: Mapped[int] = mapped_column(Integer, default=8)
    weekday: Mapped[int] = mapped_column(Integer, default=0)  # 0 = Monday
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    relevance_threshold: Mapped[float] = mapped_column(Float)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    last_run_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_tavily_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Cached embedding of the description; recomputed only when the hash changes.
    description_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="topics")
    queries: Mapped[list["TopicQuery"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan", order_by="TopicQuery.id"
    )


class TopicQuery(Base):
    __tablename__ = "topic_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(16), default=QuerySource.google_news.value)
    language: Mapped[str] = mapped_column(String(8), default="en")

    topic: Mapped[Topic] = relationship(back_populates="queries")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500))
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(LongText, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TopicArticle(Base):
    __tablename__ = "topic_articles"
    __table_args__ = (
        UniqueConstraint("topic_id", "article_id"),
        Index("ix_topic_articles_topic_id_status", "topic_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=TopicArticleStatus.candidate.value)
    digest_id: Mapped[int | None] = mapped_column(
        ForeignKey("digests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    article: Mapped[Article] = relationship()


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    content_markdown: Mapped[str] = mapped_column(LongText)
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Idempotency key of the run that produced the digest (schedule slot or manual run).
    run_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
