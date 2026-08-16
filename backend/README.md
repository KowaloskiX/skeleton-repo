# backend — FastAPI

## Running
```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
# liveness:  http://localhost:8000/api/health
# readiness: http://localhost:8000/api/health/ready
```

Configuration: `.env` at the repo root (shared) or `backend/.env` (local overrides) — see
`app/core/config.py`.

## Quality gates
```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy              # strict, src + tests
uv run pytest
uv run lint-imports      # boundary contracts (import-linter)
```

## Deployment steps
```bash
uv run ensure-indexes    # indexes + collection validators, before traffic is let in
uv run dump-openapi      # regenerates openapi.json (the source for the TS client)
```

## Docker
```bash
docker build -t skeleton-api .
docker run --rm -p 8000:8000 skeleton-api
```

Layers: `routes/` (HTTP) -> `services/` (logic) -> `repositories/` (queries) -> `models/`
(documents). The `core/domain` package is infrastructure-agnostic; all of it is enforced by
`.importlinter`.
