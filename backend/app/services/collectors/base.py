from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawArticle:
    url: str
    title: str
    source_name: str | None
    published_at: datetime | None
    snippet: str | None
    origin: str  # google_news | tavily
