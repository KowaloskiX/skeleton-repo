# Operational skills and commands (a library)

The biggest gem from the Asystent-AI codebase: **repeatable workflows written down as
skills/commands** inside the repository, versioned with the code. An AI assistant runs them
instead of improvising, and the team gets one way of doing the usual tasks.

## How we organize them

- **Skills** in `.claude/skills/<name>/SKILL.md` (a description plus instructions and optional
  scripts/`references/`). The frontmatter `description` decides when the skill activates —
  write it concretely (triggers, "use when…", "do NOT use for…").
- **Commands** (slash) in `.claude/commands/<name>.md` — shorter, imperative procedures.
- Skills are **narrow and single-purpose**; if a description contains a lot of "either/or",
  split it into separate ones.

## What this repository actually ships

Five skills in `.claude/skills/`, each written because we hit the trap it describes rather than
because a list said so:

| Skill | Why it exists |
|---|---|
| `run-dev` | The port dance (27018/6380, and 3000/8000 often taken), plus the fact that a visible element does not prove hydration. |
| `run-checks` | Gates spread across two toolchains, `pnpm ci` is not our aggregate, and pre-commit silently checks only files git knows about. |
| `scaffold-endpoint` | Layer-first means one area spans five directories **and two registries**; missing a registry fails at runtime, not at import. |
| `new-migration` | No schema does not remove the compatibility problem; a `Backward` class is mandatory and indexes are a release step. |
| `api-lookup` | Route files go stale, the generated schema cannot. |
| `query-mongo` | An ad-hoc query is written once and runs against a collection that grows for years: `countDocuments({})` scans, an unindexed sort dies at 32 MB, `skip(n)` walks n documents. |

Five commands in `.claude/commands/`, adapted from the Asystent-AI repository — the generic
ones, with the product-specific detail replaced by ours:

| Command | Why it exists |
|---|---|
| `/research` | Documents how an area works today, with `file:line`. Explicitly forbidden from suggesting changes — a documentarian, not a reviewer. |
| `/deslop` | Removes AI slop: comments restating code, defensive branches unusual for the area, casts and suppressions that dodge the type system. |
| `/code-review` | A strict maintainability audit that pushes for deleting complexity rather than rearranging it. Model invocation disabled: you ask for it deliberately. |
| `/post-mortem` | The template exists before the incident, which is the only time it can be written calmly. |
| `/fix-merge-conflicts` | Encodes which files must never be hand-merged (lockfiles, `openapi.json`, the generated client, `routeTree.gen.ts`) — regenerate instead. |

What we deliberately did **not** copy from that repository: 28 product-specific skills (tender
sources, legal rules, Elasticsearch sync) with no meaning here, its `mongo` skill (its access
runs through AWS SSO against their clusters) and `apply-design-engineering` (481 lines of
somebody else's course material — worth reading at the source, not vendoring).

The rest of this document is the wider catalogue worth building once the product has the
consumers for it.

## Starter set worth adding as the product grows

**Dev / quality:**

- `run-dev` — starts the backend (uvicorn) and the frontend (dev) on the agreed ports.
- `research` — documents existing code (the current state only, no change proposals).
- `deslop` — removes "AI slop": redundant comments, defensive try/except that is unusual for
  the area, `as any`/casts that work around the types.
- `fix-merge-conflicts` — resolves conflicts non-interactively and brings the repo back to
  build + test.
- `post-mortem` — produces an incident post-mortem document (timeline, root cause, impact,
  remediation).

**Scaffolding (per our layers):**

- `scaffold-endpoint` — a new area in the layer-first structure: a file in `routes/` (plus an
  entry in `routes/api.py`), `schemas/`, `services/`, `repositories/`, `models/` (plus an entry
  in `app/documents.py`) and a test. In a layer-first layout one area spans five directories, so
  scaffolding matters more here than under feature folders — by hand it is easy to forget the
  document registry or the `include_router` line.
- `scaffold-scheduled-report` — a recurring per-org report on a cron (if the product needs one).

**Ops / production:**

- `error-triage` — clusters errors from logs (Loki) -> a ticket (Linear) with a hypothesis and
  an owner (git blame) -> a digest on Slack.
- `assign-error-tickets` — assigns `error` tickets to the author of the code (git blame -> alias
  map -> Linear).
- `weekly-work-summary` — the Friday #shipping post: the week's plan versus merged PRs, ready to
  paste.

**Frontend review:**

- `apply-design-engineering` — design-engineering philosophy for UI polish (motion,
  micro-interactions, hover/active states).
- `web-design-guidelines` — a UI audit for accessibility and interface guidelines.
- `vercel-react-best-practices` — React/Next performance patterns during review.

**API:**

- `api-docs-lookup` — ask the live OpenAPI schema (`/openapi.json`) about endpoints and schemas
  instead of grepping route files.

## The "a skill instead of memory" rule

If you are doing something for the **second time** and it has repeatable steps or foot-guns,
write it down as a skill rather than keeping it in your head. Skills are the team's operational
memory; they grow with the product and are the best place for hard-won traps (e.g. "migrations
go through Neon's direct URL", "two clusters for test/prod").
