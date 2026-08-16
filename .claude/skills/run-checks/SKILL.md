---
name: run-checks
description: Run every quality gate the way CI does, across both toolchains. Use before committing, before opening a PR, or when the user asks whether everything passes. Also use to reproduce a CI failure locally.
---

# Run every gate

Two toolchains, four groups. Run them in this order — the cheap ones fail fastest.

## Frontend

```bash
pnpm verify        # biome ci -> tsc -> dependency-cruiser -> vitest -> vite build
```

`pnpm ci` is a **built-in pnpm command** (clean install), not our aggregate. The aggregate is
`pnpm verify`.

## Backend

```bash
cd backend
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy                 # strict, src + tests
uv run lint-imports         # 6 layer contracts
uv run pytest               # needs Docker: testcontainers starts Mongo and Redis
```

## End to end

```bash
cd frontend && WEB_PORT=3100 API_PORT=8100 pnpm test:e2e
```

Requires `docker compose up -d`. Playwright starts its own backend and frontend.

## Hooks

```bash
git add --intent-to-add .   # REQUIRED first: see below
pre-commit run --all-files
```

## Traps

- **pre-commit only sees files git knows about.** With untracked files it silently checks a
  subset — it once ran on 47 of 150 files and passed. `git add --intent-to-add .` first.
- **An API change means two regenerations**, and CI fails on the drift otherwise:
  ```bash
  cd backend && uv run dump-openapi
  pnpm --filter web generate:api
  ```
- **`notablescan` is on in tests.** A query with no index fails with `NoQueryExecutionPlans`
  rather than running slowly. That is the point: add the index to the document's
  `Settings.indexes`.
- **A failing gate is never fixed by editing its config.** Fix the code, or suppress the single
  finding with a justification in a comment.
