---
name: api-lookup
description: Answer questions about API endpoints, request or response shapes and error codes from the live schema. Use instead of grepping route files, which go stale, whenever a question is about what the API actually exposes.
---

# Ask the schema, not the files

The OpenAPI schema is generated from the running code, so it cannot drift. Route files can.

## The committed artifact

```bash
python3 -c "import json; print(*json.load(open('backend/openapi.json'))['paths'], sep='\n')"
```

## The live schema (locally, dev or test only)

```bash
curl -s "http://localhost:${API_PORT:-8000}/openapi.json" | python3 -m json.tool | head -40
```

`/docs`, `/redoc` and `/openapi.json` are **disabled outside dev/test** — in production they are
a ready-made manual for the API, complete with the error-code catalogue.

## Useful queries

```bash
# the shape of a single response
python3 -c "
import json; s = json.load(open('backend/openapi.json'))
print(json.dumps(s['components']['schemas']['CurrentUserResponse'], indent=2))"

# every error code the API can return
grep -rn 'class ApiError\|class AuthError' -A 12 backend/src/app/core/domain/errors.py
```

## The error contract

Every failure — domain, 404, 405, 422, 500, or a middleware rejection — returns the same shape:

```json
{ "code": "not_found", "message": "No such resource.", "request_id": "1bdec8c6…" }
```

`request_id` matches the `X-Request-Id` response header, so a user report maps to a log line.
Validation errors additionally carry `detail` with the field-level information.

## After changing the API

The schema and the TS client are committed, and CI fails on drift:

```bash
cd backend && uv run dump-openapi
pnpm --filter web generate:api
```
