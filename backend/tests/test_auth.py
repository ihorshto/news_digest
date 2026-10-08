from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.conftest import register


async def test_register_login_me_logout(client):
    user = await register(client, "Alice@Example.com")
    assert user["email"] == "alice@example.com"
    assert user["timezone"] == "Europe/Paris"
    assert user["telegram_linked"] is False

    me = await client.get("/api/auth/me")
    assert me.status_code == 200

    assert (await client.post("/api/auth/logout")).status_code == 204
    client.cookies.delete(get_settings().session_cookie_name)
    assert (await client.get("/api/auth/me")).status_code == 401

    bad = await client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid_credentials"

    ok = await client.post(
        "/api/auth/login", json={"email": "ALICE@example.com", "password": "password123"}
    )
    assert ok.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_session_cookie_is_httponly(client):
    resp = await client.post(
        "/api/auth/register", json={"email": "c@example.com", "password": "password123"}
    )
    cookie_header = ";".join(resp.headers.get_list("set-cookie")).lower()
    assert "nd_session=" in cookie_header
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


async def test_register_validation(client):
    short = await client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": "short"}
    )
    assert short.status_code == 422
    bad_email = await client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "password123"}
    )
    assert bad_email.status_code == 422
    bad_tz = await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "timezone": "Mars/Base"},
    )
    assert bad_tz.status_code == 422


async def test_duplicate_email(client):
    await register(client, "dup@example.com")
    resp = await client.post(
        "/api/auth/register", json={"email": "dup@example.com", "password": "password123"}
    )
    assert resp.status_code == 409


async def test_csrf_required_for_mutations(client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as raw:
        resp = await raw.post(
            "/api/auth/register", json={"email": "x@example.com", "password": "password123"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "csrf_failed"
        # Cookie present but header mismatched.
        await raw.get("/api/auth/csrf")
        resp = await raw.post(
            "/api/auth/register",
            json={"email": "x@example.com", "password": "password123"},
            headers={"X-CSRF-Token": "wrong"},
        )
        assert resp.status_code == 403


async def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 3)
    codes = []
    for _ in range(5):
        resp = await client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "password123"}
        )
        codes.append(resp.status_code)
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


async def test_update_timezone(client):
    await register(client)
    resp = await client.patch("/api/me", json={"timezone": "America/New_York"})
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "America/New_York"
    assert (await client.patch("/api/me", json={"timezone": "Nope/Nope"})).status_code == 422


def test_production_requires_strong_jwt_secret():
    import pytest

    from app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="short")
    assert Settings(environment="production", jwt_secret="x" * 40).cookie_secure is True
