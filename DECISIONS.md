# Decisions

Decisions made autonomously while building the MVP, with reasoning.

## Stack and infrastructure

- **One backend image for `api`, `worker`, `bot`.** They share models, config and services; only the command differs. Keeps the build to one Python image.
- **Nginx** (not Caddy) serves the built SPA and proxies `/api` to FastAPI. It overwrites `X-Forwarded-For` with the real peer address, so clients cannot spoof their IP to get around the auth rate limit.
- **MySQL 8.4** (8.x LTS) with `utf8mb4` / `utf8mb4_0900_ai_ci`.
- **Migrations run on `api` start** (`alembic upgrade head && uvicorn ...`). `worker` and `bot` wait for `api` to become healthy, so they never see an unmigrated schema.
- **Datetimes** are stored as naive UTC `DATETIME` and converted to aware UTC by a `UTCDateTime` type decorator, so the app never mixes naive and aware values.
- **Tests use SQLite (aiosqlite) + fakeredis.** They are fast and need no network or Docker. The real MySQL schema is exercised by the migration run in Docker and by the smoke test.

## Auth

- JWT (HS256) in an `httpOnly`, `SameSite=Lax` cookie (`Secure` when `ENVIRONMENT=production`), 7-day TTL.
- CSRF uses a **double-submit cookie**: a readable `nd_csrf` cookie plus a matching `X-CSRF-Token` header on every mutating `/api` request, login and register included. The SPA calls `GET /api/auth/csrf` once on load.
- Rate limit: a fixed 60-second window per client IP, separately for `login` and `register` (default 10/min, `RATE_LIMIT_AUTH_PER_MINUTE`).
- Login verifies against a dummy argon2 hash when the email is unknown, so response timing does not reveal which emails are registered.
