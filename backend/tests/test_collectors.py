import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import respx

from app.services.collectors.google_news import build_url, fetch_google_news, parse_feed
from app.services.collectors.tavily import FakeTavilyCollector, parse_tavily_response
from app.services.urls import normalize_url, url_hash

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_url_uses_locale_and_window():
    url = build_url("ціна біткоїна", "uk", "6h")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "when%3A6h" in url
    assert "hl=uk&gl=UA&ceid=UA:uk" in url
    assert "hl=en-US&gl=US&ceid=US:en" in build_url("bitcoin", "en", "1d")
    # unknown language falls back to English locale
    assert "ceid=US:en" in build_url("bitcoin", "xx", "1d")


def test_parse_english_feed():
    articles = parse_feed((FIXTURES / "google_news_en.xml").read_bytes())
    assert len(articles) == 8
    first = articles[0]
    assert first.url.startswith("https://news.google.com/rss/articles/")
    assert first.source_name == "Forbes"
    assert not first.title.endswith("- Forbes")
    assert first.published_at == datetime(2026, 10, 7, 10, 48, 56, tzinfo=UTC)
    assert first.origin == "google_news"
    assert all(a.title and a.published_at for a in articles)


def test_parse_ukrainian_feed():
    articles = parse_feed((FIXTURES / "google_news_uk.xml").read_bytes())
    assert len(articles) == 6
    assert any(any("а" <= ch <= "я" for ch in a.title.lower()) for a in articles)


def test_parse_feed_respects_max_items_and_garbage():
    assert len(parse_feed((FIXTURES / "google_news_en.xml").read_bytes(), max_items=3)) == 3
    assert parse_feed(b"not xml at all") == []


@respx.mock
async def test_fetch_google_news_uses_http_and_handles_errors():
    respx.get(url__startswith="https://news.google.com/rss/search").mock(
        side_effect=[
            httpx.Response(200, content=(FIXTURES / "google_news_en.xml").read_bytes()),
            httpx.Response(503),
        ]
    )
    async with httpx.AsyncClient() as client:
        ok = await fetch_google_news(client, "bitcoin price", "en", "1d")
        failed = await fetch_google_news(client, "bitcoin price", "en", "1d")
    assert len(ok) == 8
    assert failed == []


def test_parse_tavily_response():
    data = json.loads((FIXTURES / "tavily_news.json").read_text())
    articles = parse_tavily_response(data)
    assert len(articles) == 3
    hack, mica, nodate = articles
    assert hack.source_name == "reuters.com"
    assert hack.published_at == datetime(2026, 10, 7, 14, 5, tzinfo=UTC)
    assert mica.published_at == datetime(2026, 10, 7, 9, 30, tzinfo=UTC)
    assert nodate.published_at is None and nodate.snippet is None
    assert all(a.origin == "tavily" for a in articles)


async def test_fake_tavily_is_stable_within_an_hour():
    fake = FakeTavilyCollector()
    a = await fake.search("bitcoin", timedelta(hours=1), 10)
    b = await fake.search("bitcoin", timedelta(hours=1), 10)
    assert [x.url for x in a] == [x.url for x in b]
    assert len(a) == 3


def test_normalize_url_strips_tracking():
    a = "https://WWW.Reuters.com/tech/story/?utm_source=x&utm_medium=y&id=5#section"
    b = "https://reuters.com/tech/story?id=5"
    assert normalize_url(a) == normalize_url(b) == "https://reuters.com/tech/story?id=5"
    assert url_hash(a) == url_hash(b)
    assert len(url_hash(a)) == 64
    assert url_hash("https://reuters.com/a") != url_hash("https://reuters.com/b")
    # parameter order does not matter
    assert normalize_url("https://x.com/p?b=2&a=1") == normalize_url("https://x.com/p?a=1&b=2")


async def test_tavily_collector_passes_news_params(monkeypatch):
    from app.services.collectors.tavily import TavilyCollector

    collector = TavilyCollector("tvly-test")
    calls = {}

    async def fake_search(query, **kwargs):
        calls.update(kwargs, query=query)
        return json.loads((FIXTURES / "tavily_news.json").read_text())

    monkeypatch.setattr(collector._client, "search", fake_search)
    articles = await collector.search("crypto hack", timedelta(hours=6), 7)
    assert calls["topic"] == "news"
    assert calls["max_age_hours"] == 6
    assert calls["max_results"] == 7
    assert len(articles) == 3


async def test_tavily_collector_swallows_errors(monkeypatch):
    from app.services.collectors.tavily import TavilyCollector

    collector = TavilyCollector("tvly-test")

    async def boom(query, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(collector._client, "search", boom)
    assert await collector.search("x", timedelta(days=1), 5) == []
