"""Render a digest as Markdown (site history) and Telegram HTML blocks."""

import html
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

MAX_LINKS_PER_EVENT = 3
MAX_TITLE = 200
MAX_SUMMARY = 700


@dataclass
class RenderLink:
    label: str
    url: str


@dataclass
class RenderItem:
    title: str
    summary: str
    links: list[RenderLink]


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _safe_url(url: str) -> str:
    # Only http(s) links are rendered; anything else could be javascript: etc.
    return url if url.startswith(("http://", "https://")) else ""


def format_date(when: datetime, timezone: str) -> str:
    return when.astimezone(ZoneInfo(timezone)).strftime("%d.%m.%Y %H:%M")


def _md_text(text: str) -> str:
    for ch in ("\\", "[", "]", "*", "_", "`", "#"):
        text = text.replace(ch, f"\\{ch}")
    return text


def _md_url(url: str) -> str:
    return quote(url, safe=":/?&=%#@+,;~!$'.-_")


def render_markdown(topic_name: str, when_label: str, items: list[RenderItem]) -> str:
    parts = [f"# {_md_text(topic_name)}", f"_{when_label}_", ""]
    for item in items:
        parts.append(f"### {_md_text(_clip(item.title, MAX_TITLE))}")
        if item.summary:
            parts.append(_md_text(_clip(item.summary, MAX_SUMMARY)))
        links = [
            f"[{_md_text(link.label)}]({_md_url(link.url)})"
            for link in item.links[:MAX_LINKS_PER_EVENT]
            if _safe_url(link.url)
        ]
        if links:
            parts.append(" · ".join(links))
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def render_telegram_blocks(topic_name: str, when_label: str, items: list[RenderItem]) -> list[str]:
    esc = html.escape
    blocks = [f"<b>📰 {esc(topic_name)}</b>\n<i>{esc(when_label)}</i>"]
    for index, item in enumerate(items, start=1):
        lines = [f"<b>{index}. {esc(_clip(item.title, MAX_TITLE))}</b>"]
        if item.summary:
            lines.append(esc(_clip(item.summary, MAX_SUMMARY)))
        links = [
            f'<a href="{esc(link.url, quote=True)}">{esc(link.label)}</a>'
            for link in item.links[:MAX_LINKS_PER_EVENT]
            if _safe_url(link.url)
        ]
        if links:
            lines.append(" · ".join(links))
        blocks.append("\n".join(lines))
    return blocks
