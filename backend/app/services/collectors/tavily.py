"""Tavily news search collector (real and fake)."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlsplit

from app.services.collectors.base import RawArticle

logger = logging.getLogger(__name__)


class TavilySearcher(Protocol):
    async def search(self, query: str, window: timedelta, max_results: int) -> list[RawArticle]: ...


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _source_from_url(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def parse_tavily_response(data: dict) -> list[RawArticle]:
    articles = []
    for item in data.get("results", []):
        url, title = item.get("url"), (item.get("title") or "").strip()
        if not url or not title:
            continue
        content = (item.get("content") or "").strip()
        articles.append(
            RawArticle(
                url=url,
                title=title[:500],
                source_name=_source_from_url(url),
                published_at=_parse_date(item.get("published_date")),
                snippet=content[:1500] or None,
                origin="tavily",
            )
        )
    return articles


class TavilyCollector:
    def __init__(self, api_key: str):
        from tavily import AsyncTavilyClient

        self._client = AsyncTavilyClient(api_key=api_key)

    async def search(self, query: str, window: timedelta, max_results: int) -> list[RawArticle]:
        hours = max(1, int(window.total_seconds() // 3600))
        try:
            data = await self._client.search(
                query,
                topic="news",
                max_age_hours=hours,
                max_results=max_results,
                search_depth="basic",
            )
        except Exception as exc:  # the SDK raises several unrelated exception types
            logger.warning("tavily search failed for %r: %s", query, exc)
            return []
        return parse_tavily_response(data)


class FakeTavilyCollector:
    """Generates deterministic demo articles. The same hour yields the same URLs,
    so repeated runs within an hour find nothing new (exercises the empty path)."""

    async def search(self, query: str, window: timedelta, max_results: int) -> list[RawArticle]:
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        articles = []
        for i in range(min(3, max_results)):
            slug = hashlib.sha1(f"{query}|{now.isoformat()}|{i}".encode()).hexdigest()[:12]
            articles.append(
                RawArticle(
                    url=f"https://example.com/demo/{slug}",
                    title=f"[demo] {query} — update #{i + 1}",
                    source_name="example.com (demo)",
                    published_at=now - timedelta(minutes=5 * i),
                    snippet=(
                        f"Demo article generated in FAKE_TAVILY mode about {query}. "
                        "Set TAVILY_API_KEY to receive real search results."
                    ),
                    origin="tavily",
                )
            )
        return articles


def get_tavily(settings) -> TavilySearcher:
    if settings.fake_tavily:
        return FakeTavilyCollector()
    return TavilyCollector(settings.tavily_api_key)
