# Skeleton — a general-purpose product skeleton

A monorepo for a real SaaS product: **TanStack Start (TS)** + **FastAPI (Python)** +
**MongoDB**, with hand-rolled auth, provider-agnostic AI, grown-up CI/CD and enforced
architecture boundaries.

The vertical slice is already driven from the database to the form: **registration creates an
organization, sign-in works end to end**, and the TypeScript client is generated from the API
schema.

> Engineering rules: [`CLAUDE.md`](./CLAUDE.md) + [`docs/conventions/`](./docs/conventions).
> Why this stack: [`docs/PLAN.md`](./docs/PLAN.md).

## Structure

```
frontend/            TanStack Start — SSR + SPA (:3000, /api proxied -> :8000)
  src/routes/        landing, /login, /register, /app (protected)
  src/features/      feature-first; cross-feature imports go through index.ts only
  src/lib/api/       GENERATED OpenAPI client (do not edit)
backend/             FastAPI — auth, domain, DB (layer-first structure)
  src/app/routes/    endpoints + cookies + error mapping; api.py = the whole /api surface
  src/app/schemas/   the API contract (Pydantic)
  src/app/services/  business logic, transaction boundaries (no HTTP)
  src/app/repositories/  database queries + TenantScopedRepository
  src/app/models/    Beanie documents + indexes
  src/app/db/        Mongo client, base documents, transactions, collection validators
  src/app/core/      config, domain/ (pure domain), HTTP errors, rate limit, crypto, logging
  migrations/        data backfills (Beanie migrations) + README
docs/conventions/    code rules (SOLID, Python, TS, testing, git, observability, AI, skills)
```

Flat, with no `apps/` and no `packages/`: two deployable artifacts means two directories.

## Quickstart

Required: **Node 24** (`.nvmrc`) + pnpm 11 (via corepack), **Python 3.12** +
[uv](https://docs.astral.sh/uv/), Docker.

The shortest path to the right versions — [mise](https://mise.jdx.dev) reads `mise.toml` and
installs exactly what CI runs:

```bash
brew install mise            # or: curl https://mise.run | sh
mise install                 # Node 24, Python 3.12, uv 0.9.11
eval "$(mise activate zsh)"  # once in ~/.zshrc — versions then switch automatically
```

mise is **optional**: the manual path (nvm + corepack + uv) works just as well. The point of
the file is closing version drift — without it Python had only a `>=3.12` floor and the uv
version was pinned nowhere, so your local one, CI's and the Dockerfile's could be three
different versions.

Check the environment before the first run:

```bash
pnpm check-env               # versions, pin consistency, free ports, .env
```

```bash
cp .env.example .env            # AUTH_SECRET: openssl rand -hex 32
docker compose up -d            # MongoDB (replica set) :27018 + Redis :6380

# Backend (terminal 1)
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000   # indexes are created at startup (APP_ENV=dev)

# Frontend (terminal 2, from the root)
nvm use && corepack enable pnpm
pnpm install && pnpm dev        # -> http://localhost:3000
```

Open `/register`, create an organization — you land in `/app` as the `owner`.

Want to inspect the database? `docker compose --profile tools up -d` gives you `mongo-express`
on `http://localhost:8081` without installing anything. On the desktop: MongoDB Compass on
`mongodb://app:app@localhost:27018/?directConnection=true`.

## How auth works

- Passwords: **argon2id** (`pwdlib`), auto-rehash on sign-in, constant response time for a
  non-existent account. Hashing runs on a thread with a capacity limiter, so it never blocks
  the event loop.
- **Server-side sessions**: only the `sha256` of the token is stored, the cookie is `HttpOnly`
  + `SameSite=Lax` + `Secure` outside dev/test. Signing out deletes the document, i.e. revokes
  the session immediately. On top of the absolute TTL there is an idle timeout and a ceiling on
  sessions per user.
- **CSRF**: a signed double-submit cookie bound to the session. `GET /api/auth/session` issues
  `csrf_token`, the client echoes it in the `X-CSRF-Token` header. Checking happens in
  middleware, default-deny for every mutating method.
- **Rate limit** via our own middleware (on `limits`), checked **before** dependencies — so
  CSRF bounces (403) and missing sessions (401) consume budget too. A global ceiling for all
  routes plus a stricter limit on login/registration; the health probes are exempt. The counter
  lives in **Redis**, shared across replicas (`RATE_LIMIT_STORAGE_URL`); an empty URL means
  process memory. A dead Redis degrades the counter to process memory rather than switching it
  off.
- **Security headers**: CSP, HSTS (over TLS only), nosniff, frame-ancestors — set both by the
  API and by the frontend server, because a browser enforces the CSP from the response that
  delivered the document.
- Multi-tenancy: `organization_id` on the document plus a filter enforced in
  `TenantScopedRepository`, policed by a contract test. Mongo has no foreign keys, cascades or
  RLS, so cascading deletes are explicit in `AuthService.delete_user`, and tenant isolation
  rests on that repository and that test.

## Local infrastructure

`docker compose up -d` brings up two services:

| Service | Port | What for |
|---|---|---|
MongoDB (`mongodb-atlas-local`) | 27018 | the application database; replica set (transactions) + Atlas Search for future embeddings |
Redis | 6380 | the shared rate-limit counter across replicas; later also the `arq` queue |

Both ports are shifted by one from the defaults (27017, 6379), because a locally installed
`mongod`/`redis-server` wins over the Docker port and the application quietly talks to another
instance.

`docker compose --profile tools up -d` adds `mongo-express` on `http://localhost:8081`.

## The database — three non-obvious things

- **A replica set, not a standalone.** Registration creates a user, an organization, a
  membership and a session in one transaction, and multi-document transactions require a
  replica set. That is why both locally and in CI we run the `mongodb-atlas-local` image (a
  single-node RS plus Atlas Search) rather than plain `mongo`.
- **Port 27018.** A locally installed `mongod` steals 27017 from Docker and the application
  quietly talks to a different database. We deliberately dodge that trap.
- **`_id` is Mongo's `ObjectId`.** Twelve bytes instead of sixteen on every document and every
  index referencing one, and the leading timestamp makes the `_id` index a creation-time index
  for free — a collection that grows with traffic can be paged in order without a second index.
  Identifiers still leave the persistence layer as strings (`app/db/identifiers.py`), because
  the domain must not import `bson` and the API contract should not name a database type.

Indexes (uniqueness, session TTL) are the only "DDL" in Mongo, and collection validators are
the only server-side check on document shape. On dev both are applied at application startup;
on staging/prod by an explicit deployment step:

```bash
uv run ensure-indexes
```

Skipping that step used to fail nothing: the application started and every query that needed an
index quietly became a collection scan. Now the indexes are verified once at startup and the
answer is reported by `/api/health/ready`, so an instance missing them stays out of the load
balancer instead of degrading the cluster.

Locally you can go further and have the database reject an unindexed query outright — the same
guard the test suite runs under:

```bash
uv run strict-queries          # notablescan on; --off to revert
```

It refuses to touch anything that is not local, because `notablescan` is a server-wide switch.
On Atlas the equivalent is the Profiler plus an alert on slow queries.

## The type bridge, front to back

```bash
cd backend && uv run dump-openapi          # backend/openapi.json (committed)
pnpm --filter web generate:api             # frontend/src/lib/api/generated (committed)
```

CI checks that neither artifact has drifted from the code. Consume the client only through
`frontend/src/lib/api/index.ts` — dependency-cruiser enforces that.

## Quality (CI parity)

```bash
pnpm check-env                  # environment: versions, pins, ports (before debugging anything)

# TS: biome (lint+format) -> tsc -> dependency-cruiser -> vitest -> vite build
pnpm verify

# Python: ruff -> mypy strict -> import-linter -> pytest (testcontainers)
cd backend && uv run ruff check src tests scripts \
  && uv run ruff format --check src tests scripts \
  && uv run mypy && uv run lint-imports && uv run pytest

# E2E over the money path (requires docker compose up)
pnpm --filter web test:e2e

# Local hooks
uvx pre-commit install
```

Note: `pnpm ci` is a built-in pnpm command (clean install) — our aggregate of gates is
**`pnpm verify`**.

## Status

- [x] Foundation: pnpm 11 + Turborepo, Biome 2, TS strict, Node 24, CI lanes
- [x] Enforced boundaries: import-linter (**6 contracts**) + dependency-cruiser
- [x] DB: MongoDB + Beanie 2.x (async PyMongo), transactions on a replica set, indexes and
      collection validators as a deployment step
- [x] Hand-rolled auth: organizations + RBAC (owner/admin/member), server-side sessions, signed
      CSRF, rate limiting on Redis (shared across replicas)
- [x] Security: CSP/HSTS/nosniff on both layers, request body limit, docs closed outside
      dev/test, injection contracts in tests
- [x] Operations: liveness and readiness probes, `X-Request-Id` correlation, JSON logs,
      dependency vulnerability scanning in CI
- [x] OpenAPI bridge -> TS client + TanStack Query hooks, drift gate in CI
- [x] Frontend: Tailwind v4 + tokens, landing, sign-in, registration, protected route, error
      boundary, 404, expired-session handling
- [x] Tests: pytest on testcontainers, Vitest + MSW, Playwright over the money path

## What is missing, deliberately

Written down because a skeleton that hides its gaps is worse than one that has them.

- **CI has never run on a runner.** Every gate is green locally, but there is no remote and no
  pull request yet, so the workflow itself is untested — the E2E lane in particular.
- **Nothing has been deployed.** No environments, no OIDC, no database per PR. The backend image
  builds; that is as far as it goes.
- **Auth is half a product**: no email verification, no password reset, no passkeys, no TOTP, no
  audit log. Registration answers `409 email_taken`, which lets accounts be enumerated — the
  ASVS-correct generic reply needs email verification first, so the two land together.
- **Observability is logs only.** Requests correlate through `X-Request-Id` and logs are JSON,
  but there are no metrics and no traces, so "is production slow" has no answer yet.
- **No load evidence.** Beyond the argon2 measurement, nobody knows what this stack sustains.
- **Nobody has reviewed the code.** The contracts and tests were written alongside the code they
  guard; mutation testing mitigates that, it does not replace a second pair of eyes.

## Next increments

The order from [`docs/PLAN.md`](./docs/PLAN.md) section 7:

1. **CI/CD** — Environments, OIDC, previews on a separate Atlas database (`app_pr_<number>` plus
   `ensure-indexes`, dropped on close), Renovate, CodeQL, TruffleHog.
2. **Observability** — `backend/src/app/foundation/observability/` as an internal package (OTel
   behind our own API, metrics `app.<domain>.<subject>`, a `METRICS_ENABLED` gate), Sentry.
3. **AI ports** — `ChatModel`/`EmbeddingModel` Protocols plus a LiteLLM adapter, an embeddings
   collection with model/dim/version fields and an Atlas Vector Search index per model.
4. **Auth iteration 2** — email verification and password reset, then passkeys and TOTP, plus an
   audit log.

Before the first deployment: an Atlas cluster and database user, GitHub Environments
(`preview`/`staging`/`production`) with per-environment secrets and required reviewers on
production, and OIDC instead of long-lived tokens.
