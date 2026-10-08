import os

# Must be set before the app (and its cached settings) is imported.
os.environ.update(
    {
        "DATABASE_URL": "sqlite+aiosqlite://",
        "OPENAI_API_KEY": "",
        "TAVILY_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "JWT_SECRET": "test-secret-test-secret-test-secret",
        "FAKE_EMBEDDINGS": "1",
        "RATE_LIMIT_AUTH_PER_MINUTE": "1000",
    }
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.queue import get_queue  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db, make_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine):
    return make_sessionmaker(engine)


@pytest.fixture
async def db(sessionmaker):
    async with sessionmaker() as session:
        yield session


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
async def client(sessionmaker, redis, queue):
    async def _get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_queue] = lambda: queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/csrf")
        c.headers["X-CSRF-Token"] = resp.json()["csrf_token"]
        yield c
    app.dependency_overrides.clear()


async def make_client() -> AsyncClient:
    """A second, independent client (separate cookie jar) sharing the overrides."""
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    resp = await c.get("/api/auth/csrf")
    c.headers["X-CSRF-Token"] = resp.json()["csrf_token"]
    return c


async def register(client: AsyncClient, email: str = "user@example.com", password="password123"):
    resp = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


class FakeQueue:
    def __init__(self):
        self.jobs: dict[str, tuple] = {}

    async def enqueue_job(self, function, *args, _job_id=None, **kwargs):
        if _job_id in self.jobs:
            return None
        self.jobs[_job_id] = (function, args)
        return object()


@pytest.fixture
def queue():
    return FakeQueue()
