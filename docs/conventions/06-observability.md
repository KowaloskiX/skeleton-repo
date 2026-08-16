# Observability as an internal package

A gem borrowed from the Asystent-AI codebase: metrics and tracing are reached **only** through
an internal package (`backend/src/app/foundation/observability/`, and on the frontend side
`frontend/src/lib/observability/`), never through `opentelemetry` directly. That gives you one
place for conventions, one gate and the ability to change backends without touching application
code.

## Rules

- **Import from the package's public API** (`from observability.public import counter, span, …`),
  never `import opentelemetry`. An import-linter contract enforces it.
- **One metrics backend** (e.g. via OTLP -> Collector -> VictoriaMetrics/Grafana). We do not mix
  stacks.
- **A `METRICS_ENABLED` gate** — in tests and locally the metrics are a no-op; zero cost and
  zero noise.

## Naming and labels (cardinality!)

- Base name: `app.<domain>.<subject>` (e.g. `app.auth.login`, `app.ai.embedding`). Suffix
  `_total` for counters.
- **Labels carry low-cardinality enums only** (status, kind, outcome, provider). **IDs
  (user_id, tender_id, request_id) belong on spans, never in metric labels** — otherwise a
  cardinality explosion kills the backend.
- Queries over per-run counters: `sum(max_over_time(metric[window]))` — not `rate`/`increase`
  for one-shot counters.

## The "metric slice" pattern per feature

A larger feature gets its own slice of metrics with documentation:

- `emit.py` — the emitting functions (wrapping the package API), `points.py` — point
  definitions and label enums.
- **An import-linter contract** — only that slice calls the observability package for its
  domain.
- **Tests through `capture_metrics()`** — asserting that a given path emitted the right counter
  with the right labels.
- A short description: what the metric counts, its labels, how to aggregate it, and which
  Grafana panel or alert shows it.

## When to instrument

Not every change needs metrics — a small fix does not. But for a **larger feature** (a new
pipeline stage, a gate, a significant subsystem) **propose instrumentation proactively**: a
stage, an outcome or a failure mode without metrics is invisible in production. The decision
belongs to the owner — but raise it rather than skipping it quietly.

## Three signals (not just metrics)

- **Logs:** structured (JSON, `structlog`/`pino`), with `trace_id`/`span_id` injected
  automatically; no PII and no secrets (`SecretStr` helps).
- **Traces:** OTel spans, correlating log <-> trace <-> metric. IDs go on spans.
- **Errors:** Sentry on both sides (Python + TS).
- For AI, see `07-ai-evals.md` (LLM traces and costs through Langfuse/OTel GenAI).
