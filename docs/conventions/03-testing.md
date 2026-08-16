# Testing — strategy

The principle: **test behaviour, not implementation.** The pyramid: many fast unit tests of the
logic, fewer integration tests, a handful of E2E tests on the critical paths. We do not chase
100% coverage — we aim at meaningful coverage of the **domain logic**, not of glue code.

## What we test (and with what)

| Level | Scope | Backend | Frontend |
|---|---|---|---|
| **Unit** | domain logic, services, validators, pure functions | pytest | Vitest |
| **Integration** | repository + DB, API endpoints, boundaries | pytest + testcontainers (Mongo) | Vitest + MSW |
| **Component** | UI components from the user's perspective | — | Testing Library |
| **E2E** | 3–5 paths "people pay for" | Playwright | Playwright |

The E2E "money path": registration/sign-in, the key product flow, payment. Everything else
belongs lower in the pyramid.

## Backend (pytest)

- `pytest` + `pytest-asyncio` (auto mode). Async tests natively.
- HTTP: `httpx.AsyncClient(transport=ASGITransport(app=app))` — not the old
  `AsyncClient(app=...)`, and not the blocking `TestClient` for async code.
- **DB:** integration tests -> **testcontainers** with the `mongodb-atlas-local` image (a
  replica set, because of transactions). Cleanup between tests deletes documents rather than
  collections — the indexes (including unique ones) have to stay so a test sees the same
  constraints as production.
- Swap dependencies through `app.dependency_overrides` (ports -> fakes/stubs). Do not mock what
  you do not own — wrap it in a port and swap the port.
- Data factories: `polyfactory`/`factory-boy`. No hand-written dictionaries everywhere.
- Test domain exceptions and error paths, not just the happy path.

## Frontend (Vitest / Testing Library / Playwright)

- **Vitest** for logic, hooks, functions and Zod schemas.
- **Testing Library**: query elements the way a user would (`getByRole`, `getByLabelText`), not
  by `testId` unless necessary. Test behaviour, not internal state.
- **MSW** to mock the API at the network level (consistent with the generated client).
- **Playwright** only for critical end-to-end flows.

## Shared rules

- **AAA:** Arrange–Act–Assert; one logical assertion per test (one behaviour).
- A test is **deterministic and isolated** — no dependence on ordering, the clock or the
  network (mock time and I/O).
- The test name describes the behaviour:
  `rejects_registration_when_email_already_exists`.
- A test is documentation — readable beats clever. No logic (loops, ifs) inside tests.
- Red -> green -> refactor. Fixing a bug starts with a test that reproduces it.
- Coverage is a signal, not a goal; the CI gate covers domain logic, without fetishizing 100%.

## In CI

- Python lane: `pytest` (with coverage) on every PR; testcontainers
  (`mongodb-atlas-local`) for the integration tests.
- TS lane: `vitest run` + `vitest --coverage`; Playwright as a separate job (possibly on merge
  or nightly rather than on every push, if it is slow).
