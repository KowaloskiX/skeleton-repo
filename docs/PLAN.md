# A professional skeleton for a real product (SaaS) — plan for 2025/2026

**Goal:** a monorepo you can *actually build and maintain a product on* — not merely demo at a
hackathon. A **polyglot** architecture: a TypeScript frontend (TanStack Start) plus a Python
backend (FastAPI), with hand-rolled auth, grown-up CI/CD and a modern, enforced code standard.

This document is a **research-based plan** (state of the art around the turn of 2025/2026).
Sources are linked at the end of each section. The real scaffold is built from it.

> **The most important changes to know up front (2025/2026):** on the Python side **`passlib`
> and `python-jose` are dead** (passlib does not run on Py 3.13, python-jose has unpatched CVEs)
> — we use `pwdlib`/`argon2-cffi` and `PyJWT`. **`uv`** has displaced Poetry. On the TS side:
> Lucia and arctic were abandoned; **Tailwind v4**, **Zod 4** and **Biome** are mature. The
> front-to-back type bridge is **OpenAPI**, not tRPC (because the backend is Python).

---

## 1. Recommended stack (one concrete answer)

### Frontend (TypeScript)

| Layer | Choice | Why |
|---|---|---|
| Framework | **TanStack Start** | Maximum end-to-end typing (routing/loaders), ideal for app-heavy dashboards and SPAs |
| Language / config | **TypeScript `strict` + `noUncheckedIndexedAccess`** | Catches the most common runtime errors |
| API client | **OpenAPI -> `@hey-api/openapi-ts`** + the TanStack Query plugin | A typed client generated from FastAPI; end-to-end types despite two languages |
| Server data | **TanStack Query v5** | Cache, mutations, dedup; native to TanStack Start |
| UI state | **Zustand** | Ephemeral interface state (sidebar, modals, theme); light, no boilerplate |
| Validation (client) | **Zod 4** | Forms; Standard Schema compatible |
| UI | **Tailwind v4 + shadcn/ui** | The de facto standard; mix-and-match rather than a monolith |

### Backend (Python)

| Layer | Choice | Why |
|---|---|---|
| Framework | **FastAPI** | Async, automatic OpenAPI, Pydantic, excellent DX |
| Packaging / venv | **uv** (Astral) | The 2025/26 standard; one fast binary, the official template moved to uv |
| Database | **MongoDB** | Parity with the team's production stack; a flexible document means a new field without a migration; Atlas Vector Search instead of pgvector. The accepted cost: no foreign keys or cascades, no RLS, transactions require a replica set |
| ODM / DB | **Beanie 2.x** (on async PyMongo) | A document is a Pydantic model, so "one class is the schema"; **not Motor** — it is being retired in favour of async PyMongo, and Beanie 2 already sits on it |
| Migrations | **indexes: `uv run ensure-indexes`** plus Beanie data migrations | Mongo has no schema to migrate; the only "DDL" is indexes (uniqueness, TTL). Data backfills are Beanie migrations, always with a `Backward` class |
| Validation / config | **Pydantic v2 + pydantic-settings** | Schemas plus typed configuration from the environment |
| Auth | **Our own, hand-rolled** — see section 4 | Full control and learning; we write the logic |
| Async jobs | **arq** (Redis) | Retries and durability. `procrastinate` left with Postgres — Mongo has no mature equivalent, so a queue means Redis. Redis **already runs** (the shared rate-limit counter); `arq` arrives with the first real job |
| Lint / format | **Ruff** (+ **mypy**/pyright for types) | One fast binary replacing black/isort/flake8 |
| Tests | **pytest + pytest-asyncio + httpx AsyncClient** | Async-native; transactional rollback plus testcontainers |

### Shared (the whole repository)

| Layer | Choice | Why |
|---|---|---|
| Monorepo | **pnpm + Turborepo (TS) + uv (Python)** | Turborepo orchestrates TS; uv manages the Python app; one repo, two toolchains |
| Architecture | **Feature-first on the frontend, layer-first on the backend, a framework-independent service layer, explicit Result/errors** | Testable, portable logic on both sides |
| Observability | **OpenTelemetry + Sentry + Grafana Cloud** | The 2025/26 baseline, without lock-in; OTel has SDKs for Python and JS |
| Hosting | **Vercel/Netlify (web) + Railway/Render/Fly (FastAPI in Docker)** | A static/SSR frontend; the backend as a container |

*Sources: [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template), [uv vs Poetry 2025](https://medium.com/beyond-localhost/python-packaging-in-2025-uv-vs-poetry-vs-pip-tools-8dfcb98aa54e), [pwdlib](https://www.fvoron.com/blog/introducing-pwdlib-a-modern-password-hash-helper-for-python/), [hey-api + TanStack Query](https://heyapi.dev/docs/openapi/typescript/plugins/tanstack-query).*

---

## 2. Monorepo architecture (polyglot)

```
my-saas/
├── frontend/                  # TanStack Start (TS) — SSR + SPA
│   ├── src/
│   │   ├── routes/            # file-based routing (routeTree.gen.ts is generated)
│   │   ├── features/          # feature-first; cross-feature imports go through index.ts
│   │   ├── components/ui/     # the design system (shadcn/ui + Tailwind)
│   │   └── lib/api/           # the GENERATED OpenAPI client (do not edit by hand)
│   ├── .dependency-cruiser.cjs
│   ├── tsconfig.json
│   └── package.json
├── backend/                   # FastAPI (Python) — auth, domain, DB
│   ├── src/app/
│   │   ├── routes/            # HTTP: endpoints, cookies, error mapping; api.py assembles /api
│   │   ├── schemas/           # the API contract (Pydantic)
│   │   ├── services/          # business logic, transaction boundaries (no HTTP)
│   │   ├── repositories/      # database queries + TenantScopedRepository
│   │   ├── models/            # Beanie documents + indexes
│   │   ├── db/                # the Mongo client, base documents, transactions, validators
│   │   ├── core/              # config, domain/ (pure domain), HTTP errors, rate limit, crypto
│   │   ├── foundation/        # internal packages (observability, AI ports)
│   │   └── main.py
│   ├── migrations/            # data backfills (Beanie migrations) + README
│   ├── tests/
│   ├── .importlinter
│   ├── pyproject.toml         # uv
│   └── Dockerfile
├── .github/                   # CODEOWNERS + workflows/ (separate TS and Python lanes)
├── package.json / pnpm-workspace.yaml / turbo.json / biome.json
└── README.md
```

> **Flat, not `apps/`.** Two deployable artifacts means two directories at the root. There is no
> `packages/` until there is a second TS consumer: the OpenAPI client and the design system live
> in `frontend/src/`, the internal Python packages in `backend/src/app/foundation/`. Extracting
> into `packages/` is a refactor for when a second TS app appears — not a down payment.

**Rules:**

- **One owner of the database: FastAPI.** The frontend never touches the database directly —
  only through the API. (Two owners of one database is an anti-pattern — which is why Drizzle
  was dropped: data access lives on the Python side.)
- **The type bridge goes through OpenAPI, wired into CI.** The build generates
  `frontend/src/lib/api/` from the FastAPI schema (`@hey-api/openapi-ts`). The client never
  drifts from the API. Requirement: every FastAPI route has a clean `operationId` and exactly
  one tag (otherwise the generated client method names turn ugly).
- **Backend: layers (layer-first).** `routes` (HTTP only) -> `services` (logic, transaction
  boundaries, framework-agnostic) -> `repositories` (Beanie queries) -> `models` (documents);
  `schemas` is the API contract and `core/domain` the pure domain. Injection through `Depends`.
  The known downside of this layout — a change to one area touches several directories — is
  compensated by **six import-linter contracts** (among them: a route may not reach a repository
  by a shortcut).
- **Frontend: thin.** Business logic lives on the backend; the frontend renders and calls the
  API.
- **The front-to-back boundary:** serve the API on the **same origin** (e.g. `/api` through a
  proxy, or `api.yourdomain`) so the auth cookie is first-party (`SameSite`), with CORS
  configured deliberately.

*Sources: [FastAPI service-layer 2025](https://medium.com/@abhinav.dobhal/building-production-ready-fastapi-applications-with-service-layer-architecture-in-2025-f3af8a6ac563), [FastAPI generate clients](https://fastapi.tiangolo.com/advanced/generate-clients/), [Turborepo](https://turborepo.dev/docs).*

---

## 3. A state-of-the-art code standard

**Backend (Python):**

- **A service layer independent of FastAPI** — logic in plain Python (no `Request`/`Response`),
  so it also serves jobs, a CLI and unit tests without HTTP.
- **`async def` for I/O** (the database through async PyMongo, HTTP) — never a blocking driver
  inside `async def` (it kills the event loop). CPU-bound work -> `anyio.to_thread` with
  **bounded** concurrency (`CapacityLimiter`), not a plain `def`: the default 40-thread pool
  with memory-hard work (argon2 = 64 MiB per call) trades a CPU stall for memory exhaustion.
- **Pydantic v2** everywhere (request/response schemas separate from the document models);
  **pydantic-settings** for configuration.
- **Ruff** (lint + format) + **mypy**/pyright (types) + **pre-commit**. `ty`/pyrefly (fast, new)
  only as a pilot alongside mypy — not yet mature as the only gate.
- **Tests:** pytest + pytest-asyncio (auto), `httpx.AsyncClient(transport=ASGITransport(app))`,
  transactional rollback for unit tests plus testcontainers for integration. Factories
  (polyfactory/factory-boy).

**Frontend (TypeScript):**

- **TS `strict` + `noUncheckedIndexedAccess`**, `exactOptionalPropertyTypes`, `NodeNext`.
- **Biome** (lint and format in one), pre-commit hooks plus a commit-message check.
- **Feature-first**, minimal global state (Zustand), server state through TanStack Query.
- Tests: Vitest + Testing Library + MSW; Playwright on 3–5 key paths (the "money path").

**Shared:**

- **A clear state split:** server state -> TanStack Query; client/UI state -> Zustand. Do not
  mix them.
- **ADRs** for key decisions plus `CLAUDE.md`/`.cursorrules` for AI assistants.

*Sources: [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/), [mypy vs pyright vs ty](https://pydevtools.com/handbook/explanation/how-do-mypy-pyright-and-ty-compare/), [Biome vs ESLint+Prettier](https://devtoolbox.blog/biome-vs-eslint-prettier-2026-2/).*

---

## 4. Hand-rolled authentication (in Python)

Your requirement, and the right one for a product: full control over the data, no per-MAU
pricing, no lock-in. We implement auth ourselves in FastAPI, on **maintained, secure
libraries** — we do not write cryptography from scratch.

**A critical note (the 2025/2026 change):** old tutorials recommend `passlib` and `python-jose`
— **both are dead today**: `passlib` does not work on Python 3.13+ (the `crypt` module was
removed), `python-jose` has unpatched vulnerabilities. We do not build on them.

**The current, maintained toolset:**

- **Passwords: argon2id** through **`argon2-cffi`**, wrapped in **`pwdlib`** (from the author of
  FastAPI Users) — Argon2 by default, bcrypt for backwards compatibility, auto-upgrade on
  sign-in.
- **JWT: `PyJWT`** (`import jwt`) — maintained, the successor to jose. When JWE/JWK is needed ->
  JOSE via **Authlib**.
- **OAuth 2.0 / OIDC (Google, GitHub) with PKCE: `Authlib`** — the best-maintained OAuth library
  for Python, integrates with Starlette/FastAPI, PKCE, introspection, revocation.
- **Passkeys/WebAuthn: `py_webauthn`** (Duo Labs) — passwordless or as 2FA.
- **TOTP (2FA): `pyotp`**; backup codes hashed or encrypted.
- **CSRF:** required with cookies — a signed double-submit cookie plus `SameSite=Lax/Strict`.
- **Rate limiting: `limits`** plus our own middleware. *(A departure from `slowapi`, measured
  rather than assumed: on FastAPI 0.141 `SlowAPIMiddleware` does not recognize routes added via
  `include_router` and limits nothing, while its decorator counts only after dependencies and
  therefore lets through floods bounced by CSRF/401.)* Redis for multiple instances; plus a
  limit at the edge (Cloudflare/proxy).

**Patterns:**

- **Server-side sessions (an opaque session ID in an `HttpOnly`+`Secure`+`SameSite` cookie)** as
  the default for a web app — instant revocation, no foot-guns. A short access token plus a
  **revocable refresh token** (a row in the database that can be deleted). **Never tokens in
  `localStorage`** (XSS).
- **OAuth:** always Authorization Code + PKCE, exact-match redirect, `state` and `nonce`. Note:
  **Google FedCM has been mandatory since August 2025**; GitHub added PKCE (July 2025) and is
  not OIDC.
- **Passkeys** are an expected standard in 2025/26, not an extra.
- **B2B/multi-tenant:** organizations/tenants as a **first-class model from day one**, roles
  scoped per organization (RBAC), an audit log. Enterprise: SAML + OIDC + SCIM when it shows up.
- **Compliance/abuse:** anti-enumeration of accounts (generic responses, constant time), rate
  limiting on login/refresh/MFA/reset, **GDPR** (deletion within 30 days including backups, data
  export, an immutable audit log).
- **The checklist:** aim at **OWASP ASVS 5.0** (May 2025), V6/V7/V3, **Level 2**.

> A note on responsibility: hand-rolled auth means more surface for mistakes. That is why we
> hold firmly to ASVS L2, add tests and a separate security review before the first real data.
> If delivery time ever became the priority, the ready fallback (still self-hosted, data with
> us) is **FastAPI Users** or **Authentik/Ory** — without changing the database architecture.

*Sources: [pwdlib](https://www.fvoron.com/blog/introducing-pwdlib-a-modern-password-hash-helper-for-python/), [FastAPI: replace python-jose](https://github.com/fastapi/fastapi/discussions/11345), [Authlib](https://github.com/authlib/authlib), [OWASP ASVS 5.0 V6](https://github.com/OWASP/ASVS/blob/master/5.0/en/0x15-V6-Authentication.md), [cookies vs JWT 2026](https://crosscheck.cloud/blogs/cookies-vs-jwt-authentication-2026/).*

---

## 5. AI — provider-agnostic, ready to grow

The key rule: **nothing in the business logic imports a provider SDK.** AI is wired in as a
**port plus adapters**, so swapping OpenAI for Anthropic/Mistral/a local model is a
configuration change, not a rewrite. Designed for future growth (RAG, agents) without a heavy
framework at the start.

**Architecture (ports and adapters):**

- **Our own domain interfaces** (`Protocol`): `ChatModel` (`complete` + `stream`) and
  `EmbeddingModel` (`embed`, with `model_id` and `dimensions` as data). No provider imports in
  the domain layer.
- **The default adapter on `LiteLLM`** — hidden behind the port: one API for 100+ providers,
  **cross-provider fallbacks**, retries, cache, cost tracking. Business code never imports
  LiteLLM directly.
- **Provider choice through env/config**, injected via `Depends`; heavy clients created once in
  `lifespan`.
- **Pydantic AI** gets added as a separate adapter only once real **agents/tool calling**
  appear — not as the base layer.

**Structured output:** the **`instructor`** library behind a port — you define a Pydantic model
and it maps onto the best mechanism per provider (native structured output / tool calling) plus
automatic validation. Callers get a validated type regardless of provider.

**Embeddings + Atlas Vector Search (the most important schema detail):** different models mean
different dimensions and **incomparable** spaces. Therefore:

- `embedding_model`, `embedding_dim`, `embedding_version` as **first-class fields**; we never
  search across models.
- **A separate vector index per model** — an Atlas index definition hardcodes `numDimensions`
  and `similarity`, so changing the model means a new index rather than editing the old one.
  Migrating a model = a backfill on the queue -> cutting the queries over -> dropping the old
  index and field (zero downtime).
- **A `vectorSearch` index** (`$vectorSearch`, ANN over HNSW underneath),
  `quantization: "scalar"` for large sets. Locally and in CI the same API comes from the
  `mongodb-atlas-local` image, so RAG can be developed without a cloud account.
- **Watch the lock-in:** `$vectorSearch` exists only in Atlas and in the atlas-local image —
  self-hosted MongoDB Community does not have it. That is a knowingly accepted cost of choosing
  Mongo.

**Prompts outside the code:** versioned files (Jinja2/`.md`) behind a `PromptRepository` port to
start, with `prompt_version` logged on every call; **Langfuse Prompt Management** once
non-programmers start iterating on prompts.

**Reliability plus observability:** the LiteLLM Router (fallbacks, retries, cost-based routing,
cache; rate-limit state in Redis across instances). Instrumentation through the **OpenTelemetry
GenAI semantic conventions** -> Langfuse (traces, costs, evaluations) — without locking into a
specific backend.

**Async:** the whole layer is `async`; **embeddings are never computed in the request path** —
they are offloaded to a queue (`arq` on Redis).

> The effect: today you can leave AI entirely unwired (a stub adapter), and when the moment
> comes you add an adapter and a backfill rather than a rebuild. Swapping providers is an
> environment change plus a possible re-embedding.

*Sources: [LiteLLM Router](https://docs.litellm.ai/docs/routing), [Instructor](https://python.useinstructor.com/), [Atlas Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/), [Beanie ODM](https://beanie-odm.dev/), [Langfuse OTel](https://langfuse.com/integrations/native/opentelemetry), [arq](https://arq-docs.helpmanual.io/).*

---

## 6. CI/CD and DevOps (the core of the skeleton's power)

The principle: **managed platforms plus GitHub primitives** while you are small, but
**discipline (OIDC, expand-contract, feature flags, OTel) from day one**. In a polyglot monorepo
CI has **two lanes**: TS and Python.

**GitHub Actions:**

- **Split by trigger plus reusable workflows**; third-party actions pinned to a SHA.
- **TS lane:** Biome (lint+format) -> tsc (typecheck) -> Vitest -> build. pnpm store cache plus
  **Turborepo remote cache** (Vercel Remote Cache is free). Affected builds
  (`--filter=...[origin/main]`).
- **Python lane:** `uv sync` (cached) -> Ruff (lint+format) -> mypy -> pytest. Testcontainers
  with `mongodb-atlas-local` for integration tests (a replica set means transactions).
- **OpenAPI client generation in CI** — after an API change regenerate `frontend/src/lib/api/`
  and check for drift (fail on uncommitted differences). The same pattern already works for
  `routeTree.gen.ts`.
- **Concurrency:** on PRs `cancel-in-progress: true`; on deploys **`false`** (do not interrupt a
  rollout).
- **OIDC instead of long-lived secrets** — a cloud token per run, scoped to a named Environment.

**Environments (GitHub Environments):**

| Environment | Trigger | Database | Protection |
|---|---|---|---|
| **preview** | every PR | **a separate database in the Atlas cluster** (`app_pr_<number>`) | ephemeral, dropped when the PR closes |
| **staging** | merge into `main` | a separate staging database | — |
| **production** | a `v*` tag / manual approval | the production database | **required reviewers + branch restrictions** |

- Preview: a new database in the cluster -> **`uv run ensure-indexes`** -> seed -> deploy web and
  api -> a bot comments the links on the PR -> drop the database on close. Atlas has no
  copy-on-write branching, so a preview is a separate database rather than a snapshot.

**Deployment:**

- **FastAPI in Docker** (multi-stage, `python:3.12-slim`, `uv sync --frozen`, non-root,
  `HEALTHCHECK`, uvicorn workers) on Railway/Render/Fly/ECS. The TanStack Start frontend on
  Vercel/Netlify (or as a container too).
- **Indexes as a release step** (`uv run ensure-indexes`), **before** traffic reaches the new
  instances. Not from every worker at startup — which is why `APP_ENV=staging|prod` disables
  index creation at boot.
- **Zero downtime is compatibility discipline** (two versions at once -> both on the same
  schema, N/N-1). **Expand-contract migrations:** Expand -> backfill/dual write -> Contract. No
  schema does not lift that discipline: for a while two versions of the code read the same
  documents. Mongo: build indexes in the background (the default since 4.2), and new fields
  always carry a default.
- **Rolling deploys** by default; canary and metric-gated auto-rollback once you mature.
- **Feature flags** (OpenFeature + Unleash/Flagsmith/GrowthBook) — they separate deploy from
  release.

**Mongo — important details:** transactions require a **replica set** (a standalone has none),
so locally and in CI we use the `mongodb-atlas-local` image. The absence of foreign keys means
**cascading deletes live in the code** (`AuthService.delete_user`) — every new document pointing
at a user has to be added there. The absence of RLS means tenant isolation rests entirely on
`TenantScopedRepository` and a contract test.

**Observability:** OpenTelemetry (SDKs for Python and JS -> Collector -> a backend) + Sentry
(errors, on both sides) + Grafana Cloud. `/api/health` (liveness) plus `/api/health/ready`
(readiness, checking the database).

**Security in CI:** Gitleaks (pre-commit) + TruffleHog (CI) + GitHub push protection; CodeQL;
Dependabot/Renovate (TS **and** Python: `uv`/pip); an SBOM (Syft) once you mature.

*Sources: [FastAPI deploy best practices](https://render.com/articles/fastapi-production-deployment-best-practices), [MongoDB transactions](https://www.mongodb.com/docs/manual/core/transactions/), [expand-contract](https://www.tim-wellhausen.de/papers/ExpandAndContract/ExpandAndContract.html), [OpenFeature](https://openfeature.dev/).*

---

## 7. Build order for the scaffold (testable after every step)

1. **Monorepo foundation** — pnpm + Turborepo (TS), `backend/` with uv (Python), CODEOWNERS, two
   CI lanes locally.
2. **Backend: database plus the data layer** — FastAPI + Beanie on async PyMongo; docker-compose
   (`mongodb-atlas-local`) locally / Atlas in the cloud; indexes through `ensure-indexes`; seed.
3. **Backend: auth (hand-rolled)** — email and password (argon2id/pwdlib), server-side sessions
   plus cookies, middleware, RBAC/organizations, OAuth (Google/GitHub with PKCE via Authlib).
   Passkeys and TOTP in the second iteration.
4. **API plus domain** — FastAPI routers plus the service layer plus Pydantic; clean
   `operationId`s and tags for client generation.
5. **The OpenAPI bridge -> the TS client** — `@hey-api/openapi-ts` generates
   `frontend/src/lib/api/` plus TanStack Query hooks, wired into the build.
6. **Frontend** — TanStack Start + Tailwind v4 + shadcn/ui; sign-in works end to end through the
   generated client; Zustand for UI state.
7. **CI/CD** — `.github/` workflows (TS + Python + E2E lanes, previews on a separate Atlas
   database, deployment with expand-contract), Environments, OIDC, Renovate, CodeQL.
8. **Observability plus feature flags** — OTel (Python and JS) + Sentry, OpenFeature, health
   probes.
9. **AI-ready (stub)** — the `ChatModel`/`EmbeddingModel` ports plus a LiteLLM adapter plus an
   embeddings collection with model/dim/version fields and an **Atlas Vector Search** index. No
   real provider wired until needed — ready for the future.
10. **Verification** — a smoke E2E (Playwright) on the auth path plus an auth security audit
    against ASVS L2.

---

## 8. Patterns adopted from the existing repository (Asystent-AI / Minerva)

A review of that repository showed it is more mature than a typical greenfield — many rules from
this plan already work there (import-linter, the repository pattern, pydantic-settings,
testcontainers, Langfuse, evals). Below are the things worth **generalizing** into a universal
skeleton:

**Enforcing architecture boundaries (not merely a convention).** The greatest value: there, the
layers are *enforced* rather than described.

- **import-linter** (Python) with an "infrastructure-agnostic domain" contract plus a
  one-directional law of layers, checked in CI. Added to the skeleton.
- The TS counterpart: **dependency-cruiser** — the same boundaries on the frontend side.

**Code conventions worth adopting:**

- **No bare strings for categorical values** -> `StrEnum`/`Literal` (source, status, kind…). An
  excellent, concrete rule.
- **The repository pattern, strictly:** `get_db()` only in a `Depends` factory, no module-level
  singletons.
- `__init__.py` **empty by default**, importing straight from the file.
- **pydantic-settings for CLIs** (type-safe scripts) plus **`APP_ENV`** to select the
  environment (not `--env-file`).
- **Fix the lint, do not silence it** — a suppression only with a justification.

**Observability as an internal package (not raw OTel).** There, `foundation/observability` has
its own API — better than importing `opentelemetry` everywhere. Generalized: an internal
observability package with `app.<domain>.<subject>` metric naming, low-cardinality labels (enums;
IDs on spans, not in labels), a `METRICS_ENABLED` gate, tests through `capture_metrics`, and an
import-linter contract per metric slice.

**AI/LLM — maturity beyond the current plan:**

- **An evals harness** (`evals/`, dataset-driven, `APP_ENV=test`) plus the eval loop — added to
  the AI section as a full member.
- **Monitoring LLM price/cost drift in CI** (`llm-price-drift.yml` there) — an excellent idea,
  added.
- Langfuse for prompt management and traces.

**A library of operational skills — the killer feature of that repository.** Skills as versioned
repository artifacts, worth generating in the skeleton as a starter set:

- Dev/quality: `run-dev`, `research`, `deslop` (removing AI slop), `fix-merge-conflicts`,
  `post-mortem`.
- Scaffolding: `scaffold-endpoint` (a new area following the layer pattern).
- Ops: `error-triage` (Loki -> ticket -> Slack), `assign-error-tickets`,
  `scaffold-scheduled-report`, `weekly-work-summary` (#shipping).
- Frontend review: `apply-design-engineering`, `web-design-guidelines`,
  `vercel-react-best-practices`.

**Process / Git (from the rulesets):**

- Conventional Commits, a **release-impact label** (`major`/`minor`/`patch`/`no-release`), the
  `hotfix` type, and the hard rule **"never merge — only the user merges"**. The ticket-ID
  requirement stayed in that repository: it is a rule for a project with a tracker, not for a
  skeleton.
- **api-docs-lookup**: ask the live OpenAPI schema instead of grepping route files (consistent
  with our OpenAPI bridge).

**Documentation as code:** Diataxis (`docs/how-to/` + `docs/explanation/`), the **C4 model
through Structurizr DSL**, Mermaid; documentation describes **the current state only** (plans
live in issues and PRs).

**Nested `CLAUDE.md`/`AGENTS.md`** — rules per package (root + backend + frontend), not one file.

> **A divergence — settled (decision changed, 2026-08-04):** the skeleton originally stood on
> Postgres. By decision we **moved to MongoDB**, for parity with the team's production stack and
> the freedom to add fields without migrations. The frontend remains **TanStack Start** (not
> Next.js). The costs are no foreign keys or cascades, no RLS, transactions only on a
> replica set, and vectors through Atlas Vector Search instead of pgvector.

**Gems wired into the convention files**, adapted to our stack:

- **Boundary enforcement in CI** — `import-linter` (Python) + `dependency-cruiser` (TS) ->
  `05-architecture-enforcement.md`.
- **StrEnum/Literal** for categorical values, the **repository pattern** (`get_db()` only in a
  `Depends` factory), **pydantic-settings CLI** + `APP_ENV`, empty `__init__.py` ->
  `01-python-fastapi.md`.
- **Observability as an internal package** (metrics `app.<domain>.<subject>`, enum labels, IDs on
  spans, the gate, `capture_metrics` tests) -> `06-observability.md`.
- **AI + evals + LLM cost monitoring** (dataset-driven evals with `APP_ENV=test`, price drift in
  CI, the "ai_leak_guard" contract) -> `07-ai-evals.md`.
- **The skills/commands library** (`deslop`, `research`, `run-dev`, `post-mortem`,
  `scaffold-endpoint`, `error-triage`, `weekly-work-summary`, `api-docs-lookup`, UI review) ->
  `08-skills-and-commands.md`.
- **The Git process:** release-impact labels, "only the user merges", `hotfix` ->
  `04-git-pr-security.md`.
- **Docs as code** (Diataxis how-to/explanation, C4 Structurizr, Mermaid) plus nested
  `CLAUDE.md` per package.

---

## 9. Decisions (approved) and next steps

**The key decisions are already made:**

- **Frontend:** TanStack Start (TS); UI state through **Zustand**
- **Backend:** FastAPI (Python), our own implementation
- **Database:** MongoDB + Beanie 2.x on async PyMongo *(changed from Postgres — parity with the
  team's production; the backend owns the database)*
- **Auth:** hand-rolled in Python — `pwdlib`/`argon2-cffi` + `PyJWT` + `Authlib` + `py_webauthn`
- **The type bridge:** OpenAPI -> `@hey-api/openapi-ts` *(tRPC was ruled out — it is TS-only)*
- **AI:** provider-agnostic (ports plus a LiteLLM adapter), not tied to OpenAI; **Atlas Vector
  Search** for embeddings

**Next steps:**

1. Build the scaffold in the order from section 7 — the monorepo foundation -> backend (db ->
   auth -> API) -> the OpenAPI bridge -> frontend -> CI/CD.
2. Every step is testable on its own; after step 6 you have working sign-in end to end (FastAPI
   <-> TanStack Start) on a local `dev`.
3. Package it as a GitHub template ("Use this template") with `.github/` ready for secrets.

**The front-to-back boundary** is settled as the default: **FastAPI is the only backend** (auth,
DB, logic), and TanStack Start is the frontend (SSR+SPA) calling the API through the generated
client, served on the same origin (`/api`). Using the TanStack Start server layer as a thin
BFF/proxy in front of FastAPI remains an option if cookie handling ever needs it.
