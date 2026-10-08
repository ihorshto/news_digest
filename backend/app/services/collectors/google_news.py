"""Google News RSS collector.

Links point to news.google.com redirect pages; they are kept as-is (they open the
original article in a browser). Title, source and RSS description are the article text.
"""

import calendar
import html
import logging
import re
from datetime import UTC, datetime
from urllib.parse import quote_plus

import feedparser
import httpx

from app.services.collectors.base import RawArticle
from app.services.languages import GOOGLE_NEWS_LOCALES

logger = logging.getLogger(__name__)

BASE_URL = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (compatible; NewsDigest/0.1; +https://github.com/)"

_TAG_RE = re.compile(r"<[^>]+>")


def build_url(query: str, language: str, when: str) -> str:
    hl, gl, ceid = GOOGLE_NEWS_LOCALES.get(language, GOOGLE_NEWS_LOCALES["en"])
    q = quote_plus(f"{query} when:{when}")
    return f"{BASE_URL}?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _strip_source_suffix(title: str, source: str | None) -> str:
    if source and title.endswith(f" - {source}"):
        return title[: -len(source) - 3].strip()
    return title


def parse_feed(content: bytes | str, max_items: int = 100) -> list[RawArticle]:
    feed = feedparser.parse(content)
    articles: list[RawArticle] = []
    for entry in feed.entries[:max_items]:
        link = entry.get("link")
        raw_title = _clean(entry.get("title"))
        if not link or not raw_title:
            continue
        source = entry.get("source", {}).get("title") if entry.get("source") else None
        title = _strip_source_suffix(raw_title, source)
        description = _clean(entry.get("summary"))
        # The description usually repeats title + source; keep it only if it adds text.
        snippet = description
        for redundant in (title, source or ""):
            if redundant:
                snippet = snippet.replace(redundant, " ")
        snippet = re.sub(r"\s+", " ", snippet).strip()
        published = None
        if entry.get("published_parsed"):
            published = datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=UTC)
        articles.append(
            RawArticle(
                url=link,
                title=title[:500],
                source_name=source,
                published_at=published,
                snippet=snippet if len(snippet) > 20 else None,
                origin="google_news",
            )
        )
    return articles


async def fetch_google_news(
    client: httpx.AsyncClient, query: str, language: str, when: str, max_items: int = 30
) -> list[RawArticle]:
    url = build_url(query, language, when)
    try:
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("google news fetch failed for %r: %s", query, exc)
        return []
    return parse_feed(response.content, max_items=max_items)
