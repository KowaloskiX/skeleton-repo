# Architecture enforcement (boundaries in CI)

A gem borrowed from the Asystent-AI codebase: layers are not *described* — they are **enforced**
by tooling in CI. A convention nobody enforces degrades within weeks. Here boundaries are a
contract that blocks a merge.

## Backend (Python) — import-linter

The contracts live in `.importlinter` and run in the Python CI lane. Two pillars:

**1. An infrastructure-agnostic domain (a `forbidden` contract):** `core/domain/*` must not
import `db`, `routes`, FastAPI/Starlette, Beanie/PyMongo, `pwdlib` or any AI provider SDK.

**2. The law of layers (one direction):**

```
app.main         -> application assembly: middleware, router, lifespan
app.documents    -> the document registry for the ODM (must know every model)
app.routes       -> HTTP: endpoints, cookies, error mapping
app.schemas      -> the API contract (Pydantic)
app.services     -> business logic, transaction boundaries
app.repositories -> database queries
app.models       -> Beanie documents
app.db           -> the database client, base documents, transactions, the Depends provider
app.core         -> the foundation: config, domain, HTTP errors, rate limit, cryptography
```

Imports may only point **down that list**. The most common slip: the FastAPI dependency
providing the database landed in `app.core.deps` and `core` started importing `db` — which is
why it lives in `app.db.deps`.

**3. The service layer knows nothing about HTTP:** `services`, `repositories` and the
cryptography modules in `core` must not import FastAPI, Starlette or `schemas`. Without that,
logic quietly grows into `Request`/`Response` and stops being testable without HTTP.

**4. Routes do not bypass services:** `routes` must not import `repositories`, `models` or the
database client **directly** (`allow_indirect_imports = True` — through a service is fine,
shortcuts are not). This is the key contract in a layer-first structure: without it an endpoint
with a single `find_one` starts bypassing the logic layer, and a year later half the business
rules live in routers.

**5. API schemas know nothing about the database:** `schemas` must not import `services`,
`repositories`, `models`, `db`, Beanie or PyMongo — otherwise the document shape leaks into the
HTTP contract.

```ini
# .importlinter — a real excerpt, not a sketch
[importlinter:contract:layers]
name = Layers point one way
type = layers
layers =
    app.main
    app.documents
    app.routes
    app.schemas
    app.services
    app.repositories
    app.models
    app.db
    app.core

[importlinter:contract:routes_go_through_services]
name = Routes do not bypass the service layer
type = forbidden
allow_indirect_imports = True
source_modules = app.routes
forbidden_modules =
    app.repositories
    app.models
    app.db.client

[importlinter:contract:domain_agnostic]
name = The domain must be independent of infrastructure
type = forbidden
source_modules = app.core.domain
forbidden_modules =
    app.db
    app.models
    app.repositories
    app.services
    app.routes
    app.schemas
    fastapi
    starlette
    beanie
    pymongo
    pwdlib
```

Running it: `uv run lint-imports` in CI (a violation blocks the merge).

## Frontend (TS) — dependency-cruiser

The counterpart on the frontend side, in the TS CI lane:

- `features/*` do not import each other by internal paths — only through the public `index.ts`.
- No cycles (`no-circular`).
- `components/ui` (design primitives) imports neither `features/` nor `routes/`.
- The generated API client is consumed only through `src/lib/api/index.ts`.

```js
// .dependency-cruiser.cjs (excerpt)
module.exports = {
  forbidden: [
    { name: "no-circular", severity: "error", from: {}, to: { circular: true } },
    { name: "feature-isolation", severity: "error",
      from: { path: "^src/features/([^/]+)/" },
      to:   { path: "^src/features/(?!$1)[^/]+/(?!index)" } },
  ],
};
```

## The rule

Every new architectural seam (a new layer, an import ban, a bounded-context boundary) gets a
**contract** in the same PR that creates it. Without a contract the boundary does not exist —
it is only a good intention.
