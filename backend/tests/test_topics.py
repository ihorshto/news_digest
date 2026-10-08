from datetime import UTC, datetime

import pytest

from app.core.config import get_settings
from app.models import Digest
from tests.conftest import make_client, register

TOPIC = {
    "name": "Криптовалюти",
    "description": "Ціни BTC/ETH, регулювання, великі злами бірж",
    "language": "uk",
    "frequency": "daily",
    "send_hour": 9,
}


async def create_topic(client, **overrides):
    resp = await client.post("/api/topics", json={**TOPIC, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_topic_generates_queries_and_schedule(client):
    await register(client)
    topic = await create_topic(client)
    assert topic["is_active"] is True
    assert topic["relevance_threshold"] == get_settings().relevance_threshold
    assert topic["next_run_at"] is not None
    sources = {q["source"] for q in topic["queries"]}
    assert sources == {"google_news", "tavily"}
    google = [q for q in topic["queries"] if q["source"] == "google_news"]
    assert 3 <= len(google) <= 8
    # daily at 09:00 Europe/Paris => 07:00 or 08:00 UTC depending on DST
    next_run = datetime.fromisoformat(topic["next_run_at"].replace("Z", "+00:00"))
    assert next_run.astimezone(UTC).hour in (7, 8)


async def test_list_get_update_delete(client):
    await register(client)
    topic = await create_topic(client)
    listed = (await client.get("/api/topics")).json()
    assert [t["id"] for t in listed] == [topic["id"]]
    assert listed[0]["digest_count"] == 0

    resp = await client.patch(f"/api/topics/{topic['id']}", json={"is_active": False})
    assert resp.json()["is_active"] is False

    resp = await client.patch(
        f"/api/topics/{topic['id']}",
        json={"description": "Регулювання криптовалют у ЄС, MiCA, стейблкоїни"},
    )
    body = resp.json()
    assert body["description"].startswith("Регулювання")
    assert any("MiCA" in q["query"] for q in body["queries"])

    assert (await client.delete(f"/api/topics/{topic['id']}")).status_code == 204
    assert (await client.get(f"/api/topics/{topic['id']}")).status_code == 404


async def test_replace_and_regenerate_queries(client):
    await register(client)
    topic = await create_topic(client)
    resp = await client.put(
        f"/api/topics/{topic['id']}/queries",
        json=[
            {"query": "bitcoin price", "source": "google_news", "language": "en"},
            {"query": "  crypto exchange hack ", "source": "tavily", "language": "en"},
        ],
    )
    assert resp.status_code == 200
    assert [q["query"] for q in resp.json()["queries"]] == ["bitcoin price", "crypto exchange hack"]

    bad = await client.put(
        f"/api/topics/{topic['id']}/queries",
        json=[{"query": "x", "source": "bing", "language": "en"}],
    )
    assert bad.status_code == 422

    regen = await client.post(f"/api/topics/{topic['id']}/queries/regenerate")
    assert len(regen.json()["queries"]) >= 3


async def test_topic_validation(client):
    await register(client)
    for bad in (
        {"name": ""},
        {"description": "x"},
        {"frequency": "monthly"},
        {"send_hour": 24},
        {"language": "xx"},
    ):
        resp = await client.post("/api/topics", json={**TOPIC, **bad})
        assert resp.status_code == 422, bad


async def test_topic_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_topics_per_user", 2)
    await register(client)
    await create_topic(client)
    await create_topic(client)
    resp = await client.post("/api/topics", json=TOPIC)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "topic_limit_reached"


async def test_requires_auth(client):
    assert (await client.get("/api/topics")).status_code == 401
    assert (await client.post("/api/topics", json=TOPIC)).status_code == 401


async def test_users_cannot_access_each_others_topics(client):
    await register(client, "owner@example.com")
    topic = await create_topic(client)
    tid = topic["id"]

    other = await make_client()
    try:
        await register(other, "intruder@example.com")
        assert (await other.get("/api/topics")).json() == []
        assert (await other.get(f"/api/topics/{tid}")).status_code == 404
        assert (await other.patch(f"/api/topics/{tid}", json={"name": "x"})).status_code == 404
        assert (await other.put(f"/api/topics/{tid}/queries", json=[])).status_code == 404
        assert (await other.post(f"/api/topics/{tid}/queries/regenerate")).status_code == 404
        assert (await other.post(f"/api/topics/{tid}/run")).status_code == 404
        assert (await other.get(f"/api/topics/{tid}/digests")).status_code == 404
        assert (await other.delete(f"/api/topics/{tid}")).status_code == 404
    finally:
        await other.aclose()

    # Owner still has it, unchanged.
    assert (await client.get(f"/api/topics/{tid}")).json()["name"] == TOPIC["name"]


async def test_run_now_enqueues_once_per_minute(client, queue):
    await register(client)
    topic = await create_topic(client)
    first = await client.post(f"/api/topics/{topic['id']}/run")
    assert first.status_code == 202
    assert first.json()["enqueued"] is True
    second = await client.post(f"/api/topics/{topic['id']}/run")
    assert second.json()["enqueued"] is False
    assert len(queue.jobs) == 1
    function, args = next(iter(queue.jobs.values()))
    assert function == "process_topic"
    assert args[0] == topic["id"] and args[2] is True


async def test_digest_history(client, db):
    await register(client)
    topic = await create_topic(client)
    db.add(
        Digest(topic_id=topic["id"], status="fake_sent", content_markdown="# hi", article_count=2)
    )
    await db.commit()
    digests = (await client.get(f"/api/topics/{topic['id']}/digests")).json()
    assert len(digests) == 1 and digests[0]["article_count"] == 2
    listed = (await client.get("/api/topics")).json()
    assert listed[0]["digest_count"] == 1


@pytest.mark.parametrize("tz", ["America/New_York", "Asia/Tokyo"])
async def test_timezone_change_reschedules(client, tz):
    await register(client)
    topic = await create_topic(client)
    await client.patch("/api/me", json={"timezone": tz})
    updated = (await client.get(f"/api/topics/{topic['id']}")).json()
    assert updated["next_run_at"] != topic["next_run_at"]
