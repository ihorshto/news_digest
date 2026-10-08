import logging
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: str = "development"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8080"

    # Secrets / external services. Empty value => fake provider.
    openai_api_key: str = ""
    tavily_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_bot_username: str = "NewsDigestBot"
    jwt_secret: str = "change-me-in-env"

    # Explicit fake switches (forced on automatically when the key is empty).
    fake_llm: bool = False
    fake_tavily: bool = False
    fake_telegram: bool = False

    # Storage
    database_url: str = ""
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "newsdigest"
    mysql_password: str = "newsdigest"
    mysql_database: str = "newsdigest"
    redis_url: str = "redis://redis:6379/0"

    # LLM
    llm_model_fast: str = "gpt-6-luna"
    llm_model_digest: str = "gpt-6.1-sol"
    llm_timeout_seconds: float = 90.0

    # Embeddings / pipeline
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str = "/models"
    fake_embeddings: bool = False
    relevance_threshold: float = 0.38
    cluster_threshold: float = 0.85
    max_topics_per_user: int = 10
    max_events_per_digest: int = 10
    tavily_max_results: int = 10
    tavily_min_interval_minutes: int = 60
    google_news_max_items_per_query: int = 30
    http_timeout_seconds: float = 15.0

    # Auth
    jwt_ttl_hours: int = 24 * 7
    session_cookie_name: str = "nd_session"
    csrf_cookie_name: str = "nd_csrf"
    cookie_secure: bool | None = None
    rate_limit_auth_per_minute: int = 10
    telegram_link_ttl_minutes: int = 15

    default_timezone: str = "Europe/Paris"
    schedule_tick_minutes: int = Field(default=5, ge=1, le=60)

    @model_validator(mode="after")
    def _apply_fake_defaults(self) -> "Settings":
        if not self.openai_api_key:
            self.fake_llm = True
        if not self.tavily_api_key:
            self.fake_tavily = True
        if not self.telegram_bot_token:
            self.fake_telegram = True
        if self.cookie_secure is None:
            self.cookie_secure = self.environment == "production"
        return self

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"mysql+asyncmy://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    def log_fake_modes(self) -> None:
        if self.fake_llm:
            logger.warning("OPENAI_API_KEY is empty: LLM runs in FAKE mode")
        if self.fake_tavily:
            logger.warning("TAVILY_API_KEY is empty: Tavily runs in FAKE mode")
        if self.fake_telegram:
            logger.warning(
                "TELEGRAM_BOT_TOKEN is empty: Telegram runs in FAKE mode "
                "(digests are stored in the DB only)"
            )
        if self.jwt_secret == "change-me-in-env":
            logger.warning("JWT_SECRET is not set: using an insecure default")


@lru_cache
def get_settings() -> Settings:
    return Settings()
