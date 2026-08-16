---
name: scaffold-endpoint
description: Add a new API area to the layer-first backend (route, schema, service, repository, document) with its registries, indexes and tests. Use when adding an endpoint, a resource or a collection to the backend.
---

# Scaffold an API area

The backend is layer-first, so one area spans five directories plus **two registries**. Missing
a registry fails at runtime, not at import — which is exactly why this skill exists.

## The files

| Layer | File | Contains |
|---|---|---|
| HTTP | `src/app/routes/<area>.py` | endpoints only: statuses, cookies, mapping errors |
| Contract | `src/app/schemas/<area>.py` | request/response models, `StrictRequest` for input |
| Logic | `src/app/services/<area>.py` | business rules, transaction boundaries, no HTTP |
| Queries | `src/app/repositories/<area>.py` | every database call, nothing else |
| Document | `src/app/models/<area>.py` | the Beanie document plus `Settings.indexes` |

## The two registries — both are mandatory

```python
# src/app/routes/api.py
api_router.include_router(new_router)      # without it the route 404s

# src/app/documents.py
DOCUMENT_MODELS = (..., NewDocument)       # without it: CollectionWasNotInitialized
```

## What the contracts will enforce

Run `uv run lint-imports` — these fail loudly if the layering slips:

- a route importing `repositories`, `models` or the database client **directly**,
- a service or repository importing FastAPI, Starlette or `schemas`,
- a schema importing the database, Beanie or PyMongo.

## Rules that are easy to miss

- **Input is a `StrictRequest`** (`extra="forbid"`, whitespace stripped) and every field is a
  scalar. A `dict` field would accept `{"$ne": null}` and turn into NoSQL operator injection —
  `tests/test_injection_contract.py` checks this per field.
- **A tenant-owned document** carries `organization_id` with an index and is read through
  `TenantScopedRepository`. Otherwise `tests/test_tenancy_contract.py` fails: Mongo has no RLS,
  so that filter is the only isolation there is.
- **Every filtered field needs an index.** The test server runs with `notablescan`.
- **Identifiers are `ObjectId` in the database and strings everywhere else.** A reference field
  is a `PydanticObjectId`; a service signature and a schema take `str`. Convert through
  `app.db.identifiers` — a query built from an unconverted string matches nothing and raises
  nothing.
- **Never `to_list()` without a ceiling** — use `bounded_to_list(query, what=...)`.
- **A document pointing at a user** must be deleted in `AuthService.delete_user`, inside the
  transaction. `tests/test_cascade_contract.py` discovers it automatically and fails until then.
- **A transaction callback must be replayable** (Mongo retries it). Hash passwords and send
  email *before* entering the transaction.
- **`operation_id` and exactly one tag** per route, otherwise the generated TS client gets ugly
  method names. `tests/test_openapi_contract.py` enforces it.

## Finish

```bash
cd backend && uv run dump-openapi
pnpm --filter web generate:api      # both artifacts are committed; CI fails on drift
```
