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

## LLM

- **Provider: OpenAI Responses API** (`openai` SDK 3.x, `client.responses.parse(..., text_format=PydanticModel)`), which sends a strict `json_schema` (Structured Outputs). Everything sits behind the `LLMClient` protocol (`expand_topic`, `write_digest`) in `backend/app/services/llm.py`; the fake client implements the same protocol.
- **Model names `gpt-6-luna` / `gpt-6.1-sol` are used as given** (`LLM_MODEL_FAST` / `LLM_MODEL_DIGEST`). Without an API key they could not be checked against the live API. If OpenAI rejects a name, change it in `.env`; no code change is needed.
- **The schemas sent to the model carry no constraints** (no `minItems` and the like), because strict mode supports only a subset of JSON Schema. Counts (3–8 queries), dedup and language codes are checked in `normalize_expansion()`. An invalid answer gets one retry, then the topic name is used as the query.
- **Topic expansion returns two lists.** 3–8 short Google News queries (English always included) plus 1–2 descriptive English queries for Tavily. Tavily is billed per call, so it gets fewer queries.
- **The digest uses structured output too:** `{items: [{event_id, title, summary}]}`. **Links are never produced by the model.** The system attaches source URLs by `event_id`, so the model cannot invent or alter a link, and every item is guaranteed to have one. Unknown or duplicate `event_id`s are dropped.
- **Prompt-injection hardening.** Article text and topic text are HTML-escaped before they go inside `<article>`/`<topic>` tags, so content cannot close or forge a tag. The system prompt says the tagged content is data. No tools are passed to the model.
- **There is no separate per-article summary call.** The digest model summarizes each event directly from title + snippet, which saves one LLM call per article. `articles.summary` caches the summary the digest produced for the event's lead article.
- **If the LLM fails while writing a digest** (API error, refusal, no usable items), the digest is still built with the extractive fake writer (headline + first sentence), and the error is recorded in `digests.error`. The reader still gets the news, and the failure is visible in the history.

## Relevance and clustering (calibration)

Calibration used the real model (`paraphrase-multilingual-MiniLM-L12-v2`): 3 topics (crypto in Ukrainian, AI in Ukrainian, football in English), 15 relevant headlines in EN/UK, and the other topics' headlines plus 7 unrelated headlines as negatives.

| Scoring | relevant min / mean | off-topic max / mean |
|---|---|---|
| similarity to description only | 0.19 / 0.35 | 0.22 / 0.12 |
| **max over description + queries** | **0.32 / 0.51** | **0.26 / 0.10** |

- Description-only scoring overlaps (a relevant MiCA story scored 0.19, while "petrol prices rose" scored 0.22 against crypto). So **relevance = max cosine similarity to the topic profile = [description, *google_news queries]**. The profile vectors are cached on the topic (`description_embedding`) and recomputed only when the profile text hash changes.
- **`RELEVANCE_THRESHOLD` defaults to 0.30**, the middle of the gap between 0.26 and 0.32. Per-topic override is available in the UI under "Додатково". Every scored article is logged at DEBUG, and a summary at INFO, for further calibration.
- **`CLUSTER_THRESHOLD` defaults to 0.80, not 0.85.** Clear same-event pairs (two outlets, same story) scored 0.83–0.85, and the same story across EN/UK scored 0.72, so 0.85 would almost never merge anything. Different events on the same subject ("BTC climbs" vs "BTC falls") scored 0.58. Known false positive: very short headlines with the same entities ("Arsenal beat Chelsea" / "Chelsea beat Arsenal") scored 0.89.
- Clustering is **complete-linkage**: an article joins an event only if it is similar to every member. Single-linkage would chain loosely related stories into one event.

## Scheduling and idempotency

- **Slots are wall-clock hours in the user's timezone** (DST-aware via `zoneinfo`): hourly means every local hour; 6h means 4 slots aligned to `send_hour` (e.g. 9 → 03/09/15/21); daily means `send_hour`; weekly means `send_hour` on `weekday` (0 = Monday). A timezone change in settings reschedules all of the user's topics.
- **Cron tick every 5 minutes** (`run_at_startup=True`) enqueues `process_topic` for active topics with `next_run_at <= now`, using `_job_id = topic:{id}:slot-YYYYMMDDTHHMM` (the slot start). Repeated ticks and retries map to the same job id. arq refuses duplicates while the job is queued or running, and for 1 h after it finishes (`keep_result`).
- **Three more layers against double sending:** (1) a scheduled run returns early if `next_run_at` is already in the future (the slot was handled); (2) the digest row with a unique `run_key = "{topic_id}:{slot}"` is committed *before* sending to Telegram, so a crashed or retried job cannot send the same digest again; (3) a per-topic Redis lock (`SET NX EX`, 15 min) stops a manual run and a scheduled run from processing the same topic at once. The other job is retried 30 s later.
- **"Send now"** uses `run_key = manual-YYYYMMDDHHMM`: one manual run per topic per minute. Repeated clicks are no-ops. A manual run ignores pause and schedule and does not move `next_run_at`.
- **If the worker was down**, a missed slot runs once at the next tick and the next slot is computed from "now" (no catch-up storm). A scheduled run that crashes moves on to the next slot (`last_run_status = "error: ..."`) instead of retrying forever.
- **Freshness:** articles older than the frequency window (+30 min slack for tick lag) are dropped, and candidates that miss one run go stale and are marked `filtered`.
- **Already-sent exclusion:** besides the per-topic `sent` status (same URL), a new article is also dropped when its embedding is ≥ `CLUSTER_THRESHOLD` similar to any article sent for this topic in the last 3 days (same event from another outlet).
- **Delivery statuses:** `sent`, `fake_sent` (FAKE_TELEGRAM), `no_chat` (no linked Telegram: stored in history, articles are marked sent so they are not resent forever), `failed` (articles stay candidates and are retried at the next run while still fresh). "Bot blocked" clears `telegram_chat_id`, sets `telegram_blocked_at`, and the site shows a warning.
- **Articles are stored once** across topics with `INSERT IGNORE` (MySQL) / `ON CONFLICT DO NOTHING` (SQLite), so concurrent jobs do not clash on `url_hash`.
