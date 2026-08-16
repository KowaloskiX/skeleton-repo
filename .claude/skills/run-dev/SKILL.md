---
name: run-dev
description: Start the local stack (MongoDB, Redis, FastAPI, TanStack Start) and verify it is actually serving. Use when the user asks to run the app, start the servers, or check that localhost works. Also use before manual testing or E2E runs.
---

# Run the local stack

Order matters: the database has to be healthy before the backend starts, because the backend
creates indexes at boot on `APP_ENV=dev`.

## 1. Infrastructure

```bash
docker compose up -d          # MongoDB on 27018, Redis on 6380
docker compose ps             # both must say "running"
```

The ports are shifted by one from the defaults on purpose. A locally installed `mongod` or
`redis-server` occupies 27017/6379 and **wins over the Docker port**, so the application
quietly talks to a different instance. If a connection behaves strangely, check this first:

```bash
lsof -nP -iTCP:27017 -sTCP:LISTEN
```

## 2. Ports for the app

3000 and 8000 are frequently taken by another project on the same machine. Check before
starting, and fall back to 3100/8100:

```bash
pnpm check-env                # versions, pin consistency, free ports, .env
```

Both the Vite config and the Playwright config read `WEB_PORT` and `API_PORT`, so one pair of
variables moves everything consistently.

## 3. Servers

```bash
# backend
cd backend && uv run uvicorn app.main:app --port "${API_PORT:-8000}" --reload

# frontend (from the repo root)
WEB_PORT="${WEB_PORT:-3000}" API_PORT="${API_PORT:-8000}" pnpm dev
```

Run them in the background and **verify**, do not assume:

```bash
curl -s "http://localhost:${API_PORT:-8000}/api/health"        # {"status":"ok",...}
curl -s "http://localhost:${API_PORT:-8000}/api/health/ready"  # every dependency "up"
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:${WEB_PORT:-3000}/"
```

## Optional: strict queries

```bash
cd backend && uv run strict-queries      # notablescan on; --off to revert
```

The local database then rejects any query without an index, the same way the test suite does —
useful while clicking through a feature. It refuses to run against a non-local URL.

## Traps

- **`rate_limit_storage: not_configured` in readiness** means there is no `.env`, so the rate
  limiter counts in process memory even though Redis is running. `cp .env.example .env` and
  restart the backend.
- **A stale dev server survives edits badly.** After large refactors, restart it rather than
  debugging phantom behaviour.
- **A visible element does not prove hydration.** The header is server rendered, so it appears
  long before React attaches handlers. When scripting the browser, wait for `networkidle`
  before clicking anything.
