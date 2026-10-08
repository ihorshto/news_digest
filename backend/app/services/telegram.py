"""Outgoing Telegram messages via the Bot API (worker side)."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096


class TelegramError(Exception):
    pass


class BotBlockedError(TelegramError):
    """The chat can no longer receive messages (bot blocked, chat deleted, ...)."""


class TelegramSender(Protocol):
    async def send_html(self, chat_id: int, text: str) -> None: ...


_UNREACHABLE_MARKERS = (
    "bot was blocked by the user",
    "user is deactivated",
    "chat not found",
    "bot was kicked",
    "bot can't initiate conversation",
)


class HttpTelegramSender:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None):
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._client = client or httpx.AsyncClient(timeout=20)

    async def send_html(self, chat_id: int, text: str) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        for attempt in range(3):
            try:
                response = await self._client.post(self._url, json=payload)
            except httpx.HTTPError as exc:
                raise TelegramError(f"network error: {exc}") from exc
            data = response.json() if response.content else {}
            if response.status_code == 200 and data.get("ok"):
                return
            description = str(data.get("description", response.text))[:300]
            if response.status_code == 429 and attempt < 2:
                retry_after = int(data.get("parameters", {}).get("retry_after", 1))
                await asyncio.sleep(min(retry_after, 30))
                continue
            if response.status_code in (400, 403) and any(
                marker in description.lower() for marker in _UNREACHABLE_MARKERS
            ):
                raise BotBlockedError(description)
            raise TelegramError(f"{response.status_code}: {description}")
        raise TelegramError("rate limited")


@dataclass
class FakeTelegramSender:
    """Records messages instead of sending them (FAKE_TELEGRAM / tests)."""

    sent: list[tuple[int, str]] = field(default_factory=list)

    async def send_html(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))
        logger.info("FAKE_TELEGRAM: message to %s (%d chars) not sent", chat_id, len(text))


def split_message(blocks: list[str], limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Pack HTML blocks into messages under `limit` chars, never splitting inside a block.

    Blocks are self-contained (every tag opened in a block is closed in it), so each
    message stays valid HTML. A single oversized block is a rendering bug upstream;
    it is still truncated defensively at a line boundary.
    """
    messages: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > limit:
            lines, block = block.split("\n"), ""
            for line in lines:
                if len(block) + len(line) + 1 > limit:
                    break
                block = f"{block}\n{line}" if block else line
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            messages.append(current)
            current = block
    if current:
        messages.append(current)
    return messages
