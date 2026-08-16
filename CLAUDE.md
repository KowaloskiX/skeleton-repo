# CLAUDE.md — engineering rules for this project

> This file is read by humans and by AI assistants (Claude, Cursor) alike. It is the **source
> of truth** for how we write code in this repository. Assistants: apply these rules without
> asking; if something conflicts with a user request, flag the conflict rather than quietly
> breaking a rule.

## Stack (short version)

- **Frontend:** TanStack Start (TS `strict`) + TanStack Query (server state) + Zustand (UI
  state) + Tailwind v4 + shadcn/ui.
- **Backend:** FastAPI (Python 3.12+) + Beanie 2.x on async PyMongo + Pydantic v2. Packaging:
  `uv`.
- **Database:** MongoDB (Atlas in the cloud, `mongodb-atlas-local` locally and in CI).
  Transactions require a replica set; vectors go through Atlas Vector Search.
- **Type bridge:** OpenAPI -> `@hey-api/openapi-ts` (a generated client, never hand-edited).
- **Auth:** our own, hand-rolled (`pwdlib`/`argon2-cffi`, `PyJWT`, `Authlib`, `py_webauthn`).
- **AI:** provider-agnostic (ports plus a LiteLLM adapter).

## Rules in brief (full versions in `docs/conventions/`)

1. **The domain layer knows no framework.** Business logic in plain Python/TS — no
   `Request`/`Response`, no provider SDK imports. The framework is a detail at the edge.
2. **Dependencies point inwards** (ports and adapters). The domain defines interfaces;
   infrastructure implements them. **Boundaries are ENFORCED in CI** (import-linter /
   dependency-cruiser), not merely described.
3. **Types are a contract.** `strict` in TS, full type hints plus mypy in Python. No `any` and
   no `# type: ignore` without a justification in a comment.
4. **No bare strings for categorical values** (status, kind, source…) -> `StrEnum`/`Literal`
   (Python), literal unions (TS).
5. **Validation at the boundary.** Input is validated by Pydantic (backend) / Zod (frontend).
   Inside the system we trust the types.
6. **Errors are explicit, not hidden.** Expected failures as a result type, not as surprise
   exceptions. Exceptions are for genuinely exceptional situations.
7. **Small, unambiguous units.** A function or class does one thing (SRP). Prefer composition
   over inheritance.
8. **YAGNI + KISS.** We do not build for an imagined future; we build simple, extensible
   things. Exception: deliberate seams (ports) where change is certain (AI, payments).
9. **Testability is a design requirement**, not an add-on. If something is hard to test, that
   is usually a sign of a bad design.
10. **Fix the lint, do not silence it.** `# noqa`/`eslint-disable` only for a genuine false
    positive, with a justifying comment. Never edit the linter config to make a check pass.
11. **Only a human merges.** The assistant opens PRs and pushes branches — never merges into
    `main`/`test`.
12. **Observability through an internal package** (`foundation/observability`), never
    `opentelemetry` directly.
13. **Identifiers are `ObjectId`, and they stop at the persistence layer.** We chose Mongo, so
    we use its identifier rather than paying for portability we do not plan. It does not reach
    the domain or the API: `app/db/identifiers.py` converts to and from strings, because
    `core/domain` must not import `bson` and the contract should not name a database type. The
    accepted cost: an identifier in a URL reveals its creation time, and a raw query built from
    an unconverted string matches nothing silently.
14. **The database does not guard integrity — you do.** Mongo has no foreign keys, cascades or
    RLS: cascading deletes are explicit in the service and inside a transaction, tenant
    isolation goes solely through `TenantScopedRepository`, and uniqueness solely through
    indexes. Every new collection passes `tests/test_tenancy_contract.py`.
15. **Everything in the repository is written in English** — code, comments, docs, commits, UI
    copy. Product translations are a separate layer (i18n), never comments in another language.

## Detailed documents

- [`docs/conventions/00-principles.md`](docs/conventions/00-principles.md) — SOLID, DRY/KISS/YAGNI, composition, layer separation, ports and adapters, error handling.
- [`docs/conventions/01-python-fastapi.md`](docs/conventions/01-python-fastapi.md) — Pydantic v2, async, layers, DI, MongoDB/Beanie, StrEnum, pydantic-settings CLI, Ruff/mypy.
- [`docs/conventions/02-typescript-frontend.md`](docs/conventions/02-typescript-frontend.md) — strict TS, Zod, TanStack Query vs Zustand, components, feature folders.
- [`docs/conventions/03-testing.md`](docs/conventions/03-testing.md) — the testing strategy on both sides.
- [`docs/conventions/04-git-pr-security.md`](docs/conventions/04-git-pr-security.md) — Conventional Commits, branch naming, release labels, the PR standard, ASVS.
- [`docs/conventions/05-architecture-enforcement.md`](docs/conventions/05-architecture-enforcement.md) — import-linter (Python) + dependency-cruiser (TS): enforcing layers and boundaries in CI.
- [`docs/conventions/06-observability.md`](docs/conventions/06-observability.md) — observability as an internal package: metrics, labels, the gate, tests.
- [`docs/conventions/07-ai-evals.md`](docs/conventions/07-ai-evals.md) — AI ports, dataset-driven evals, LLM cost drift monitoring, Langfuse.
- [`docs/conventions/08-skills-and-commands.md`](docs/conventions/08-skills-and-commands.md) — the library of operational skills/commands (starter).

> **Nested `CLAUDE.md` files:** `backend/`, `frontend/` and larger internal packages
> (`backend/src/app/foundation/observability/`) may carry their own `CLAUDE.md` with local
> rules. This file is the root; local ones add detail.

## Definition of Done (every PR)

- [ ] Types pass (`mypy` / `tsc`), lint and format clean (`ruff` / `biome`).
- [ ] Tests added/updated and green; domain logic covered.
- [ ] Input validated at the boundary; no secrets in the code.
- [ ] Clear names, short functions, no dead code and no commented-out blocks.
- [ ] API change -> the generated OpenAPI client regenerated and committed.
- [ ] Data/index changes follow expand-contract and are reversible (a new field always has a
      default; a Beanie migration ships with a `Backward` class).
- [ ] Boundary contracts pass (import-linter / dependency-cruiser).
- [ ] Commit in Conventional Commits format; PR carries exactly one release-impact label
      (`major`/`minor`/`patch`/`no-release`).
- [ ] The merge is left to the user (the assistant does not merge).
