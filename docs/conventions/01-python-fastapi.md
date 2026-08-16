# Python / FastAPI / Pydantic — conventions

Python 3.12+, `uv`, FastAPI, MongoDB through Beanie (async PyMongo), Pydantic v2. Lint/format:
**Ruff**. Types: **mypy** (strict).

## Structure: layer-first

```
backend/src/app/
├── routes/          HTTP: endpoints, cookies, mapping errors onto statuses
│   ├── api.py       assembles the whole /api router — one place with the full API surface
│   ├── auth.py      the /api/auth/* endpoints
│   ├── health.py    liveness and readiness probes
│   ├── cookies.py   setting the session and CSRF cookies
│   ├── errors.py    AuthError -> HTTP status
│   └── dependencies.py  service factories, CurrentUser
├── schemas/         the API contract (Pydantic): request/response
├── services/        business logic, transaction boundaries — NO HTTP
├── repositories/    database queries, returning documents
│   └── base.py      TenantScopedRepository (tenant enforcement)
├── models/          Beanie documents plus index declarations
├── db/              the Mongo client, base documents, transactions, collection validators
├── core/            config, domain, error mapping, rate limit, cryptography, logging
│   └── domain/      pure Python: Result, roles, identity, error codes
├── documents.py     the document registry for Beanie
└── main.py          application assembly
```

**The deliberate trade-off of this layout.** Layer-first gives one place with the whole HTTP
surface (`routes/api.py`) and a readable split of responsibilities, but it has a known downside:
**a single change in one area touches four directories**, and removing an area means hunting
through the tree (the alternative is feature folders, where an area is one directory). We
compensate with import-linter contracts — see `05-architecture-enforcement.md`:

- `routes` must not import `repositories` or `models` **directly** (no shortcuts to the database
  from an endpoint),
- `services`/`repositories` must not import FastAPI or `schemas`,
- `schemas` must not import the database or the logic,
- `core/domain` must not import anything from the edge.

Verified by mutation: adding `from app.models.auth import User` to `routes/health.py` breaks the
`routes_go_through_services` contract.

A router contains NO logic. A service knows nothing about `Request`/`Response`. A repository
contains NO business rules.

## Type hints — mandatory

- Full annotations everywhere (arguments, returns). `mypy --strict` has to pass.
- 3.12 syntax: `list[str]`, `X | None` (not `Optional`), `type` instead of `Type`.
- No `Any` without justification; `# type: ignore[code]` only with a specific code and a comment
  explaining why.

## Categorical values -> StrEnum / Literal (never a bare `str`)

A value from a closed set (status, kind, source, mode, visibility…) is a **`StrEnum`**
(preferred) or at minimum a `Literal[...]` — never a bare `str`. This covers the field type,
constants and comparisons.

```python
# WRONG — stringly typed; typos and drift pass silently
source: str = "user"
if file.source == "scraped": ...

# RIGHT — StrEnum: type-checked, enumerable, self-documenting
class FileSource(StrEnum):
    SCRAPED = "scraped"
    USER = "user"

source: FileSource
if file.source is FileSource.SCRAPED: ...
```

Use `Literal[...]` only where an enum is impractical (an external contract). Define the enum or
alias once and import it — do not scatter raw literals across call sites.

## Pydantic v2 — good practices

- **Separate the models:** `schemas/` (the API contract) is not `models/` (the database
  document). Both are Pydantic, so the temptation to return the document directly is stronger
  than with an ORM — do not: the document carries `password_hash` and internal fields.
- Schema variants per operation: `UserCreate`, `UserUpdate`, `UserRead`. Not one model for
  everything.
- `model_config = ConfigDict(...)`: for read models built from an ORM -> `from_attributes=True`.
  Consider `frozen=True`/`extra="forbid"` on input.
- Validation is a business boundary: use `Field(..., gt=0, max_length=...)`,
  `field_validator`/`model_validator` for rules. Do not duplicate those rules deeper down.
- **Configuration only through `pydantic-settings`** (`BaseSettings`) in `core/config.py`, read
  from the environment; one `Settings` object, injected as a dependency. No `os.getenv`
  scattered through the code.
- Special types instead of `str`: `EmailStr`, `AnyUrl`, `SecretStr` (for passwords and tokens —
  they do not log themselves by accident).

## Async — rules

- **I/O-bound endpoints -> `async def`.** The database through async PyMongo, HTTP calls async.
- **Never blocking code inside `async def`** (a sync DB driver, `time.sleep`, heavy CPU) — it
  kills the event loop.
- **CPU-bound: `to_thread` + `CapacityLimiter`, not a plain `def`.** A plain `def` in FastAPI
  goes to the default 40-thread pool — for memory-hard work (argon2: 64 MiB per call) that
  trades a CPU stall for memory exhaustion. The pattern: the blocking version private, the
  public `async` one offloading to threads through a shared limiter. Pick the limit **by
  measurement**; for argon2 it came out as `cores / parallelism` (see the table in
  `core/security.py`).
- **The limiter is per process.** With `--workers N` the peak memory use is
  `N × limit × cost`. Do that arithmetic before choosing the worker count.
- **Measure loop lag, not HTTP latency.** Latency under load conflates "the loop is blocked"
  with "the loop is busy". A monitor ticking every 5 ms separates the two — the pattern lives in
  `tests/test_security_concurrency.py`.
- **Set timeouts explicitly.** PyMongo's default 30 s for server selection means a dead database
  hangs for half a minute and piles up requests. We use 5 s for server selection and a 10 s
  budget per operation (CSOT).
- Create heavy clients (HTTP, pools) once in `lifespan`, not per request. `@app.on_event` is
  deprecated.
- Long or retryable jobs (emails, embeddings) -> a **queue** (`arq` on Redis), not
  `BackgroundTasks` and not inline. Redis already runs in compose (it holds the rate-limit
  counter); `arq` arrives with the first real job.

## Dependency injection through `Depends`

- Provide services and repositories through `Depends` — easy to swap in tests
  (`app.dependency_overrides`).
- The database session as a dependency (one per request, closed in `finally`).
- The service layer depends on **ports** (Protocol/ABC), not on concrete adapters — the
  implementation is chosen by the factory in `Depends`, based on config.

```python
class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...

class RegisterUser:
    def __init__(self, users: UserRepository, emailer: EmailSender) -> None:
        self._users = users
        self._emailer = emailer
    async def __call__(self, data: UserCreate) -> UserRead: ...
```

## Repository pattern — strictly

- All data access goes through a **repository**. Services and routers neither build filters nor
  call collections directly.
- A repository abstracts database details — method signatures are domain-shaped
  (`get_active_by_org(org_id)`), not raw queries.
- **Call the session/`get_db()` only in the `Depends` factory** that constructs the repository —
  never inside the repository or the service. **No module-level singletons** of repositories.

```python
# WRONG — a module-level singleton
database = Database.from_settings(get_settings())
user_service = UserService(database)

# RIGHT — a Depends factory (Database lives in the lifespan, not in the module)
def get_user_service(database: DbDep, settings: SettingsDep) -> UserService:
    return UserService(database, settings)
```

## `__init__.py` — empty by default

Leave `__init__.py` empty unless module initialization genuinely requires otherwise. By default
import straight from the file (`from app.services.auth import AuthService`) rather than
re-exporting through `__init__`.

## pydantic-settings CLI + `APP_ENV`

- Build scripts and CLIs on **`pydantic-settings`** (type-safe arguments, validation, help from
  docstrings). Subcommands as a `BaseModel` with `async def cli_cmd(self)`; the aggregator
  inherits from `BaseSettings`.
- Select the environment through the **`APP_ENV`** variable (`APP_ENV=test uv run python -m ...`),
  not through `--env-file`. Evals and tests always run with `APP_ENV=test` — never against
  production.

## MongoDB through Beanie (async)

- A document is a Pydantic model (`class User(TimestampMixin, UUIDDocument)`). A new field
  **must** have a default — existing documents do not carry it, and that freedom is exactly why
  we chose Mongo.
- **`_id` is Mongo's `ObjectId`** (Beanie's default). We use Mongo deliberately, so we use its
  identifier: 12 bytes rather than 16, and the leading timestamp turns the primary key into a
  creation-time index. Sort by `-_id` instead of adding an index on `created_at`.
- **`ObjectId` stops at the persistence layer.** `app/db/identifiers.py` converts: `to_text` on
  the way out, `to_object_id` on the way in (returning `None` for a malformed value, so a typo
  in a URL is a 404 rather than a 500), `identifier_of` to narrow Beanie's optional `id`. The
  domain and the API speak in strings — `domain_agnostic` forbids `bson` in `core/domain`, and
  the contract should not name the database.
- **A raw query needs the converted value.** `find({"user_id": "<string>"})` matches nothing and
  raises nothing. When writing one outside a repository, convert first.
- Queries live only in `repositories/`. A service receives documents; it does not build filters.
- **The transaction boundary sits in the service** (`await self.db.in_transaction(...)`), and
  every write inside receives `session=` — without it the write escapes the transaction and
  commits quietly. Transactions require a replica set.
- **No foreign keys and no cascades.** Deleting related documents is explicit in the service
  (`AuthService.delete_user`) and covered by a transaction. A new document pointing at a user
  means adding it there.
- **No Row-Level Security.** Tenant isolation rests entirely on `TenantScopedRepository` and the
  `tests/test_tenancy_contract.py` contract test.
- Declare indexes in `Settings.indexes`. They are the only "DDL" we have: uniqueness and TTL
  stand on them. On dev they are created at application startup, on production by
  `uv run ensure-indexes` as a deployment step (which also applies the `$jsonSchema` collection
  validators).
- Data migrations: the Beanie CLI with `Forward`/`Backward` classes, in the **expand-contract**
  style (see `04-git-pr-security.md`), always reversible. Details:
  `backend/migrations/README.md`.
- Add a new document to `app/documents.py`, otherwise Beanie will not register it.

## Mongo queries — rules

The database has no foreign keys, no RLS and no planner that would warn you. These rules are
**enforced by tests** rather than by good will (see `tests/test_query_contract.py`).

- **Filter only on indexed fields.** The test server runs with `notablescan`, so a collection
  scan ends in `NoQueryExecutionPlans` — a missing index fails a test rather than production. A
  new field in a filter means a new `IndexModel` in the document's `Settings.indexes`.
- **Never `to_list()` without a ceiling.** Use `bounded_to_list(query, what=...)` from
  `app.repositories.base`: it fetches `limit + 1` and **logs an error** when the threshold is
  hit. Silently truncating a result is worse than having no limit, because nobody finds out.
- **Queries live only in `repositories/`.** A route must not reach for a model as a shortcut —
  the `routes_go_through_services` contract in import-linter enforces that.
- **Do not build filters from raw input** and do not use `$where` — that is NoSQL injection.
  Build filters from typed Beanie expressions (`User.email == value`).
- **Two simple reads often beat a `$lookup`.** `organizations_for_user` runs two indexed queries
  instead of an aggregation — clearer and faster on small sets. Reach for an aggregation when
  you genuinely need server-side joining, and then measure with `explain()`.
- **Inside a transaction, operations run sequentially.** A Mongo client session is not safe for
  concurrent queries — concurrency is allowed only outside a transaction
  (`asyncio.TaskGroup`).
- **Transactions through `Database.in_transaction`, never a manual `start_transaction`.** Mongo
  requires retrying transactions labelled `TransientTransactionError` (e.g. `WriteConflict`);
  `with_transaction` does that for us. The manual version returned 500 on two concurrent
  registrations.
- **A transaction callback must be replayable** — it may run more than once. Password hashing,
  sending email and anything else expensive or irreversible happens BEFORE entering the
  transaction.
- **An existence check is not a safeguard.** There is a race between `find_one` and `insert` —
  the only safeguard is a unique index, so handle `DuplicateKeyError` and use `keyPattern` to
  tell which index broke.
- **Timeouts and the pool are explicit**: 5 s for server selection, a 10 s budget per operation
  (CSOT), and a stated `maxPoolSize`. PyMongo's defaults are 30 s and 100 connections — the
  second one is invisible until `workers * replicas * pool` exceeds the cluster limit.
- **Declared indexes are verified at startup** and reported through `/api/health/ready`. A
  deployment that skipped `ensure-indexes` then stays out of the load balancer instead of
  turning every query into a collection scan.
- **Locally, run `uv run strict-queries`** to have the database reject unindexed queries the way
  the test suite does.
- **Pagination rather than a bigger ceiling.** When `bounded_to_list` starts logging
  truncations, the response needs pagination, not a raised limit.

## Ruff + mypy + pre-commit

- **Ruff** = lint + format (it replaces black/isort/flake8). Enable a solid rule set
  (`E,F,I,UP,B,SIM,ASYNC,…`).
- **mypy** strict in CI; aim for zero `ignore`s.
- **pre-commit** runs ruff (check + format) and mypy before a commit; the same runs in CI (the
  Python lane).

## What we do not do

- Logic in a router; database queries in a service; returning a document model from the API.
- `print` for logging (we use a structured logger plus OTel).
- Global mutable state; `os.getenv` outside `Settings`.
- Catching `Exception` without re-raising or handling it.
