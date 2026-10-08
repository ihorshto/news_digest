"""LLM access behind a small interface so the provider can be swapped in one place."""

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from pathlib import Path
from string import Template
from typing import Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.services.languages import LANGUAGE_NAMES_EN, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

MIN_QUERIES = 3
MAX_QUERIES = 8
MAX_TAVILY_QUERIES = 2


# ---- Structured output schemas (kept constraint-free for strict JSON schema mode) ----


class LLMQuery(BaseModel):
    query: str
    language: str


class TopicExpansionOut(BaseModel):
    google_news_queries: list[LLMQuery]
    tavily_queries: list[str]


class DigestItemOut(BaseModel):
    event_id: int
    title: str
    summary: str


class DigestOut(BaseModel):
    items: list[DigestItemOut]


# ---- Domain types ----


@dataclass
class GeneratedQuery:
    query: str
    source: str  # google_news | tavily
    language: str


@dataclass
class EventArticle:
    title: str
    url: str
    source_name: str | None
    snippet: str | None
    published_at: datetime | None


@dataclass
class EventInput:
    event_id: int
    articles: list[EventArticle] = field(default_factory=list)


@dataclass
class DigestItem:
    event_id: int
    title: str
    summary: str


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    async def expand_topic(
        self, name: str, description: str, language: str
    ) -> list[GeneratedQuery]: ...

    async def write_digest(
        self, topic_name: str, topic_description: str, language: str, events: list[EventInput]
    ) -> list[DigestItem]: ...


# ---- Prompt helpers ----


@cache
def load_prompt(name: str) -> Template:
    return Template((PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"))


def _esc(text: str | None) -> str:
    """Escape untrusted text so it cannot close or forge the XML-like wrapper tags."""
    return html.escape(text or "", quote=False)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES_EN.get(code, code)


def render_expand_prompts(name: str, description: str, language: str) -> tuple[str, str]:
    system = load_prompt("expand_topic_system").substitute()
    user = load_prompt("expand_topic_user").substitute(
        name=_esc(name),
        description=_esc(description),
        language=language,
        language_name=language_name(language),
    )
    return system, user


def render_events(events: list[EventInput]) -> str:
    blocks = []
    for event in events:
        parts = [f'<event id="{event.event_id}">']
        for article in event.articles:
            published = article.published_at.isoformat() if article.published_at else "unknown"
            parts.append(
                "<article>\n"
                f"<title>{_esc(article.title)}</title>\n"
                f"<source>{_esc(article.source_name or 'unknown')}</source>\n"
                f"<published>{published}</published>\n"
                f"<text>{_esc(article.snippet)}</text>\n"
                "</article>"
            )
        parts.append("</event>")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def render_digest_prompts(
    topic_name: str, topic_description: str, language: str, events: list[EventInput]
) -> tuple[str, str]:
    system = load_prompt("digest_system").substitute(language_name=language_name(language))
    user = load_prompt("digest_user").substitute(
        topic_name=_esc(topic_name),
        topic_description=_esc(topic_description),
        events=render_events(events),
    )
    return system, user


# ---- Validation shared by all providers ----


def normalize_expansion(out: TopicExpansionOut, topic_language: str) -> list[GeneratedQuery]:
    """Validate and clean the model output. Raises LLMError when unusable."""
    seen: set[str] = set()
    queries: list[GeneratedQuery] = []
    for item in out.google_news_queries:
        text = re.sub(r"\s+", " ", item.query).strip()[:300]
        lang = item.language.lower()[:2]
        if lang not in SUPPORTED_LANGUAGES:
            lang = "en" if text.isascii() else topic_language
        if text and text.lower() not in seen:
            seen.add(text.lower())
            queries.append(GeneratedQuery(text, "google_news", lang))
    queries = queries[:MAX_QUERIES]
    if len(queries) < MIN_QUERIES:
        raise LLMError(f"expected at least {MIN_QUERIES} queries, got {len(queries)}")
    for text in out.tavily_queries[:MAX_TAVILY_QUERIES]:
        text = re.sub(r"\s+", " ", text).strip()[:300]
        if text:
            queries.append(GeneratedQuery(text, "tavily", "en"))
    return queries


def fallback_queries(name: str, language: str) -> list[GeneratedQuery]:
    return [
        GeneratedQuery(name, "google_news", language),
        GeneratedQuery(name, "tavily", language),
    ]


def validate_digest(out: DigestOut, events: list[EventInput]) -> list[DigestItem]:
    known = {e.event_id for e in events}
    items: list[DigestItem] = []
    used: set[int] = set()
    for item in out.items:
        if item.event_id in known and item.event_id not in used and item.title.strip():
            used.add(item.event_id)
            items.append(DigestItem(item.event_id, item.title.strip(), item.summary.strip()))
    return items


# ---- OpenAI implementation ----


class OpenAILLMClient:
    def __init__(self, settings: Settings, http_client=None):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
            http_client=http_client,
        )
        self._fast = settings.llm_model_fast
        self._digest = settings.llm_model_digest

    async def _parse(self, model: str, system: str, user: str, schema: type[BaseModel]):
        import openai

        try:
            response = await self._client.responses.parse(
                model=model,
                instructions=system,
                input=user,
                text_format=schema,
            )
        except openai.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        parsed = response.output_parsed
        if parsed is None:
            raise LLMError("model returned no parsable output (refusal or empty)")
        return parsed

    async def expand_topic(self, name: str, description: str, language: str):
        system, user = render_expand_prompts(name, description, language)
        last_error: Exception | None = None
        for attempt in (1, 2):  # one retry on invalid output
            try:
                out = await self._parse(self._fast, system, user, TopicExpansionOut)
                return normalize_expansion(out, language)
            except (LLMError, ValidationError) as exc:
                last_error = exc
                logger.warning("expand_topic attempt %s failed: %s", attempt, exc)
        logger.error("expand_topic falling back to topic name: %s", last_error)
        return fallback_queries(name, language)

    async def write_digest(self, topic_name, topic_description, language, events):
        system, user = render_digest_prompts(topic_name, topic_description, language, events)
        out = await self._parse(self._digest, system, user, DigestOut)
        items = validate_digest(out, events)
        if not items:
            raise LLMError("digest model returned no usable items")
        return items


# ---- Fake implementation (no API key) ----


def _first_sentence(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


class FakeLLMClient:
    """Deterministic stand-in used when OPENAI_API_KEY is empty and in tests."""

    async def expand_topic(self, name: str, description: str, language: str):
        phrases = [p.strip() for p in re.split(r"[,:;.\n]+", description) if len(p.strip()) > 2]
        candidates = [name, *phrases]
        out = TopicExpansionOut(
            google_news_queries=[LLMQuery(query=c, language=language) for c in candidates],
            tavily_queries=[f"{name}: {phrases[0]}" if phrases else name],
        )
        try:
            return normalize_expansion(out, language)
        except LLMError:
            return fallback_queries(name, language)

    async def write_digest(self, topic_name, topic_description, language, events):
        items = []
        for event in events:
            lead = event.articles[0]
            summary = _first_sentence(lead.snippet or lead.title)
            items.append(DigestItem(event.event_id, lead.title, summary))
        return items


def get_llm_client(settings: Settings) -> LLMClient:
    if settings.fake_llm:
        return FakeLLMClient()
    return OpenAILLMClient(settings)
