#!/usr/bin/env bash
# End-to-end smoke test in FAKE mode (no API keys needed):
# builds and starts the full stack in an isolated compose project, registers a user,
# creates a topic, presses "send now" and waits for the digest to appear in history.
#
# Usage: scripts/smoke_test.sh            (tears everything down afterwards)
#        KEEP=1 scripts/smoke_test.sh     (leave the stack running for inspection)
# Needs: docker compose v2, curl, python3. Network access is needed on the first run
# (Docker images, the embedding model, Google News RSS).
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT="${SMOKE_PROJECT:-nd-smoke}"
PORT="${SMOKE_PORT:-18080}"
BASE="http://localhost:${PORT}"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.yml -f scripts/docker-compose.smoke.yml)
JAR="$(mktemp)"
UP_LOG="$(mktemp)"
export SMOKE_PORT="$PORT"

log() { printf '\033[1;34m[smoke]\033[0m %s\n' "$*"; }
fail() {
  printf '\033[1;31m[smoke] FAIL:\033[0m %s\n' "$*" >&2
  "${COMPOSE[@]}" logs --tail 60 api worker >&2 || true
  exit 1
}
cleanup() {
  rm -f "$JAR" "$UP_LOG"
  if [[ "${KEEP:-0}" != "1" ]]; then
    log "tearing down"
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  else
    log "KEEP=1: stack left running at $BASE (project $PROJECT)"
  fi
}
trap cleanup EXIT

json() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }

log "building and starting the stack (project $PROJECT, port $PORT)"
if ! "${COMPOSE[@]}" up -d --build --wait --wait-timeout 300 >"$UP_LOG" 2>&1; then
  tail -40 "$UP_LOG" >&2
  fail "stack did not become healthy"
fi

log "waiting for the API through nginx"
for _ in $(seq 1 60); do
  curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$BASE/api/health" | grep -q '"ok"' || fail "health check failed"

CSRF="$(curl -fsS -c "$JAR" -b "$JAR" "$BASE/api/auth/csrf" | json 'd["csrf_token"]')"
api() { # method path [json-body]
  local args=(-sS -c "$JAR" -b "$JAR" -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json"
    -X "$1" -w '\n%{http_code}')
  [[ $# -ge 3 ]] && args+=(-d "$3")
  curl "${args[@]}" "$BASE$2"
}
expect() { # expected-status response
  local status body
  status="$(tail -n1 <<<"$2")"
  body="$(sed '$d' <<<"$2")"
  [[ "$status" == "$1" ]] || fail "expected HTTP $1, got $status: $body"
  printf '%s' "$body"
}

EMAIL="smoke-$(date +%s)-$RANDOM@example.com"
# Bodies are built in variables: bash 3.2 (macOS) mangles escaped quotes inside "$(...)".
REGISTER_BODY='{"email":"'"$EMAIL"'","password":"smoke-password-1"}'
BAD_LOGIN_BODY='{"email":"'"$EMAIL"'","password":"wrong-password"}'
OTHER_BODY='{"email":"other-'"$EMAIL"'","password":"smoke-password-1"}'
log "registering $EMAIL"
expect 201 "$(api POST /api/auth/register "$REGISTER_BODY")" >/dev/null
expect 200 "$(api GET /api/auth/me)" | json 'd["email"]' | grep -q "$EMAIL" || fail "me mismatch"

log "checking that a wrong password is rejected"
expect 401 "$(api POST /api/auth/login "$BAD_LOGIN_BODY")" >/dev/null

log "creating a topic"
TOPIC="$(expect 201 "$(api POST /api/topics '{"name":"Криптовалюти","description":"Криптовалюти: ціни BTC/ETH, регулювання, великі злами бірж","language":"uk","frequency":"daily","send_hour":9}')")"
TOPIC_ID="$(json 'd["id"]' <<<"$TOPIC")"
QUERIES="$(json 'len(d["queries"])' <<<"$TOPIC")"
[[ "$QUERIES" -ge 2 ]] || fail "expected generated queries, got $QUERIES"
log "topic $TOPIC_ID created with $QUERIES generated queries"

log "editing queries and pausing/resuming"
expect 200 "$(api PUT "/api/topics/$TOPIC_ID/queries" '[{"query":"bitcoin price","source":"google_news","language":"en"},{"query":"Криптовалюти біткоїн","source":"google_news","language":"uk"},{"query":"crypto exchange hack","source":"tavily","language":"en"}]')" >/dev/null
expect 200 "$(api PATCH "/api/topics/$TOPIC_ID" '{"is_active":false}')" | json 'd["is_active"]' | grep -q False || fail "pause failed"
expect 200 "$(api PATCH "/api/topics/$TOPIC_ID" '{"is_active":true}')" | json 'd["is_active"]' | grep -q True || fail "resume failed"

log "pressing \"send now\""
expect 202 "$(api POST "/api/topics/$TOPIC_ID/run")" | json 'd["enqueued"]' | grep -q True || fail "run was not enqueued"

log "waiting for the digest (first run downloads the embedding model)"
DIGESTS="[]"
for _ in $(seq 1 90); do
  DIGESTS="$(expect 200 "$(api GET "/api/topics/$TOPIC_ID/digests")")"
  [[ "$(json 'len(d)' <<<"$DIGESTS")" -ge 1 ]] && break
  STATUS="$(expect 200 "$(api GET "/api/topics/$TOPIC_ID")" | json 'd["last_run_status"]')"
  [[ "$STATUS" == error* ]] && fail "worker reported: $STATUS"
  [[ "$STATUS" == "empty" ]] && fail "run found no relevant articles (is the network available?)"
  sleep 2
done
[[ "$(json 'len(d)' <<<"$DIGESTS")" -ge 1 ]] || fail "no digest after 180s"

STATUS="$(json 'd[0]["status"]' <<<"$DIGESTS")"
COUNT="$(json 'd[0]["article_count"]' <<<"$DIGESTS")"
LINKS="$(json 'd[0]["content_markdown"].count("](http")' <<<"$DIGESTS")"
[[ "$STATUS" == "fake_sent" ]] || fail "unexpected digest status $STATUS"
[[ "$COUNT" -ge 1 && "$LINKS" -ge 1 ]] || fail "digest has no articles/links"
log "digest stored: status=$STATUS, articles=$COUNT, links=$LINKS"

log "checking that another user cannot see the topic"
CSRF_SAVE="$CSRF"; : >"$JAR"
CSRF="$(curl -fsS -c "$JAR" -b "$JAR" "$BASE/api/auth/csrf" | json 'd["csrf_token"]')"
expect 201 "$(api POST /api/auth/register "$OTHER_BODY")" >/dev/null
expect 404 "$(api GET "/api/topics/$TOPIC_ID/digests")" >/dev/null
CSRF="$CSRF_SAVE"

log "checking the web UI is served"
curl -fsS "$BASE/" | grep -q '<div id="root">' || fail "index.html not served"
curl -fsS "$BASE/topics/$TOPIC_ID/history" | grep -q '<div id="root">' || fail "SPA fallback broken"

printf '\033[1;32m[smoke] PASS\033[0m\n'
