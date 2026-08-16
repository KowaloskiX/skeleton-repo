# AI: abstraction, evals and costs

This combines our plan (provider-agnostic) with the maturity of the Asystent-AI codebase
(evals, price monitoring). The goal: AI that is swappable, measurable and cost-controlled.

## Abstraction (a reminder)

- The domain depends only on the `ChatModel` / `EmbeddingModel` ports (Protocols). No business
  code imports a provider SDK.
- The default adapter is built on **LiteLLM** (fallbacks, retries, cost tracking), behind the
  port. `instructor` for structured output.
- **The "ai_leak_guard" import-linter contract:** `core/domain` must not import
  `openai`/`anthropic`/`litellm`.
- Prompts live outside the code (files/Jinja) behind a `PromptRepository` port, and
  `prompt_version` is logged on every call.

## Evals — first-class, not an add-on

Changing a prompt, a model or an AI pipeline without an eval is guesswork. The pattern:

- An **`evals/`** directory with datasets (`evals/data/`) and scripts run with **`APP_ENV=test`**
  — never against production.
- **Dataset-driven:** inputs plus expectations/scorers; the result is a metric (accuracy, F1,
  cost, latency), not "looks fine".
- **The eval loop:** change -> eval -> compare against the baseline -> decide. A regression in
  the eval blocks the change.
- Langfuse as the store for datasets, scores and traces; scorers can be deterministic or
  LLM-as-judge.

## Cost monitoring / LLM price drift

A gem: a dedicated CI job (`llm-price-drift.yml` in the Asystent-AI repo) that watches costs so
they cannot quietly run away:

- Track the price per model and the estimated cost per key path; alert when drift exceeds a
  threshold.
- LiteLLM natively counts cost and tokens per request — aggregate that into metrics (see
  `06-observability.md`) and into Langfuse.
- Cost-based fallbacks: mix a frontier model with a cheap one (Haiku/Flash) wherever the cheap
  one suffices.

## Async and the queue

- The whole AI layer is `async`. **Embeddings and generation never sit in the request path** —
  offload them to a queue (`arq` on Redis; `procrastinate` required Postgres and left with it).
- Backfilling embeddings after a model change: a new field and a **new vector index** per model
  (an Atlas index definition hardcodes `numDimensions`) -> backfill on the queue -> cut the
  queries over -> drop the old one (zero downtime; see the Atlas Vector Search section of the
  plan).

## Reliability

- Retry + timeout + fallback across providers (the LiteLLM Router); a Redis-backed rate limit
  when running several instances.
- Structured output is always validated (Pydantic/`instructor`) — we do not trust raw text from
  a model.
- LLM traces through the OTel GenAI semantic conventions -> Langfuse (without locking into one
  backend).
