# Git, PRs and security

## Git and commits

- **Conventional Commits.** `type: description` or `type(scope): description`. Types: `feat`,
  `fix`, `chore`, `hotfix`, `refactor`, `test`, `docs`, `revert`. Breaking -> `!`.
  - Examples: `feat(auth): add passkey registration`, `fix: do not echo the password in the 422
    response`.
  - Regex: `^(feat|fix|chore|hotfix|refactor|test|docs|revert)(\([A-Za-z0-9._-]+\))?!?: .+`
  - **The scope is optional** and names an area of the code (`auth`, `ci`, `db`), not a ticket
    number. If your project has a tracker with mandatory IDs, tighten the regex in
    `scripts/check-commit-message.sh` — every other rule stays unchanged.
- **Branch name:** short kebab-case describing the change (`session-idle-timeout`,
  `fix-csrf-rotation`). No `feat/...`, no user prefix.
- The `commit-msg` hook (`scripts/check-commit-message.sh`, wired through pre-commit) enforces
  the message format.
- **One release-impact label per PR (exactly one):** `major` (breaking), `minor` (a new visible
  feature), `patch` (a fix or small change), `no-release` (docs/cleanup). Chosen by impact, not
  by the kind of work.
- **Only a human merges.** The assistant creates and pushes PRs, **never** `gh pr merge` and
  never a merge into `main`/`test`.
- **Trunk-based:** short-lived branches off a freshly pulled `main`. Small, frequent PRs. One PR
  is one coherent change; squash-merge (the PR title becomes the commit subject, so it must
  follow the format).
- `main` is protected: a PR is required, CI green, at least one review, no direct pushes.
- **API:** check parameters and schemas against the live OpenAPI schema (the `api-docs-lookup`
  skill) rather than by grepping route files (those go stale).

## The PR standard

- **Small and focused** (ideally under ~400 diff lines). A large PR means a weak review.
- Description: *what*, *why*, *how to test*; links to the task; screenshots for UI.
- Green CI (types, lint, tests) **before** review. You do not ask for review on red.
- Self-review before sending: read your own diff.
- API change -> the generated OpenAPI client regenerated, in the same PR.
- Document-shape change -> a data migration (Beanie, with a `Backward` class) in the same PR;
  an index change -> visible in `Settings.indexes`.

### Reviewer checklist

- [ ] Compliance with the rules (`00`–`03`): layers, types, validation, error handling.
- [ ] Tests cover the new logic and the error paths.
- [ ] No secrets, no logging of sensitive data, input validated.
- [ ] Clear names, no dead or commented-out code, no `any`/`type: ignore` without a reason.
- [ ] Performance impact (N+1 queries, a missing index) thought through.

## Migrations: expand-contract (zero downtime)

Never break the schema in one step. Three separately deployed phases:

1. **Expand** — add additively (a new nullable column or one with a non-volatile default, a new
   table). The old code keeps working.
2. **Migrate/backfill** — dual writes plus a batched data backfill.
3. **Contract** — remove the old thing only once all traffic has switched over and been
   verified.

Mongo safely: the absence of a schema does **not** lift this discipline — for a while two
versions of the code read the same documents, so a new field always has a default and the old
one is removed only after the cutover. Indexes build in the background (by default since 4.2),
but on a large collection they cost I/O — create them as a release step
(`uv run ensure-indexes`), not at application startup.

## Security — baseline rules

- **Secrets only in the environment / GitHub Environments.** The repository holds only
  `.env.example`. `.env` is in `.gitignore`. Presence of variables is validated at startup
  (`Settings`).
- **Validate every input** (Pydantic/Zod) at the boundary. Build filters from typed Beanie
  expressions, never by concatenating `$where` or injecting raw input into query operators
  (NoSQL injection).
- **Auth:** argon2id passwords (`pwdlib`); tokens/sessions in an `HttpOnly`+`Secure`+`SameSite`
  cookie, never in `localStorage`. Rate limiting on login/refresh/MFA/reset. Anti-enumeration of
  accounts (generic responses, constant time).
- **Authorization on every request** — check permissions and tenant on the server; never trust
  the client. RBAC scoped per organization.
- **Headers and CORS** set deliberately; the API on the same origin as the frontend (a
  first-party cookie).
- **Dependencies:** Renovate/Dependabot (TS and Python), pinning, `pnpm audit`/`pip-audit` in
  CI.
- **Secrets in CI:** OIDC instead of long-lived tokens; Gitleaks (pre-commit) + TruffleHog (CI);
  CodeQL.
- **Logs:** no PII, passwords or tokens (`SecretStr` helps); structured logs plus `trace_id`
  correlation.
- **GDPR:** account deletion (within 30 days, backups included), data export, an immutable audit
  log of security events.

## Auth security checklist (OWASP ASVS 5.0, Level 2)

The target is **ASVS L2**, chapters V6 (Authentication), V7 (Session), V3 (Cryptography). The
minimum to tick off:

- [ ] Passwords: at least 12 characters allowed, no composition rules, no periodic rotation;
      checked against breaches (the HIBP range API).
- [ ] argon2id hashing with parameters at or above the OWASP recommendation; no bcrypt for new
      passwords.
- [ ] Session: ID regeneration after sign-in and after a privilege change; idle plus absolute
      timeout; server-side revocation on sign-out.
- [ ] OOB/TOTP codes: single-use, bound to the request, rate-limited.
- [ ] OAuth: Authorization Code + PKCE, exact-match redirect, `state` and `nonce` validated.
- [ ] Password reset / email verification: a single-use token, short TTL, hashed in the
      database, invalidated after use.
- [ ] Rate limiting and lockout on every sensitive endpoint.
- [ ] Audit log: sign-in, password change, MFA change, role change, account deletion.
