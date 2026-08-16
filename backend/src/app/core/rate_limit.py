"""Rate limiting as middleware — deliberately our own, not `slowapi`.

**Why not slowapi.** Verified on FastAPI 0.141 + Starlette 1.3:
- `SlowAPIMiddleware` recognizes a route via `hasattr(route, "endpoint")`, but FastAPI wraps
  `include_router` in an `_IncludedRouter` object that lacks that attribute. The middleware
  never finds a handler, treats the request as exempt and **limits nothing**.
- The `@limiter.limit` decorator wraps the endpoint function, so it counts only AFTER
  dependencies resolve. CSRF rejections (403) and missing sessions (401) never reached the
  counter — meaning the cheapest floods stayed unlimited.

Here the limit is checked before dependencies, for every route, with the rules in one place.

**Storage is pluggable** (`RATE_LIMIT_STORAGE_URL`):
- empty -> process memory; the limit applies **per instance**. Good for tests and single-node.
- `redis://…` -> one shared counter for all replicas. The target setting for staging/prod.
- `mongodb://…` -> shared as well, without adding Redis, but every request becomes a write to
  the document database. An emergency exit, not a default.

**Behind a proxy** set `TRUSTED_PROXY_HOPS` to the number of your own proxies in front of the
application — see `client_key`. Without it all traffic from nginx looks like a single client
and the login limit becomes a global limit for everybody at once.

**Known limitations:**
- The key is an IP address, which is a blunt instrument: users behind one NAT share a budget.
  Per-account limits are a separate layer, not built yet. We deliberately do NOT key on the
  session cookie: its value cannot be verified without a database query, so an attacker would
  draw a fresh cookie per request and enjoy an unlimited budget.
"""

import logging
import re
import time
from dataclasses import dataclass
from ipaddress import ip_address
from re import Pattern

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Match
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.domain.errors import ApiError
from app.core.errors_http import error_response

logger = logging.getLogger(__name__)

# Liveness and readiness probes: a throttled probe looks like an application outage to the
# orchestrator, and a rolling update then starts killing healthy pods.
RATE_LIMIT_EXEMPT_PATHS = frozenset({"/api/health", "/api/health/ready"})

_UNKNOWN_CLIENT = "unknown"
_ASYNC_SCHEME_PREFIX = "async+"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """The name is part of the counter key, so rules do not eat each other's budget.

    `per_route` decides how wide that budget is:

    - `True` — one counter per route, so hammering one endpoint does not spend the budget for
      the rest of the API. This is what a general ceiling should do.
    - `False` — one counter for every path the rule matches. Deliberate for `auth-write`:
      alternating between login and registration must not double an attacker's budget.
    """

    name: str
    methods: frozenset[str] | None
    path: Pattern[str]
    item: RateLimitItem
    per_route: bool = False

    def matches(self, method: str, path: str) -> bool:
        if self.methods is not None and method not in self.methods:
            return False
        return self.path.search(path) is not None


def build_rate_limit_rules(settings: Settings) -> tuple[RateLimitRule, ...]:
    """First matching rule wins. The last one is a catch-all, so **every** route is limited by
    default — a new endpoint cannot ship without coverage."""
    return (
        RateLimitRule(
            name="auth-write",
            methods=frozenset({"POST"}),
            path=re.compile(r"^/api/auth/(login|register)$"),
            item=parse(settings.login_rate_limit),
        ),
        RateLimitRule(
            name="global",
            methods=None,
            path=re.compile(r".*"),
            item=parse(settings.global_rate_limit),
            per_route=True,
        ),
    )


def build_rate_limit_storage(settings: Settings) -> Storage:
    """An empty URL means process memory. Otherwise Redis/Mongo — a counter shared by replicas.

    We accept a plain `redis://…` (what a provider hands you) and add the `async+` prefix
    ourselves, which is how `limits` picks the asynchronous implementation. Without it you get
    a storage backend that blocks the event loop.
    """
    url = settings.rate_limit_storage_url
    if not url:
        return MemoryStorage()
    if not url.startswith(_ASYNC_SCHEME_PREFIX):
        url = _ASYNC_SCHEME_PREFIX + url
    storage = storage_from_string(url)
    if not isinstance(storage, Storage):  # pragma: no cover - configuration error
        raise TypeError(f"RATE_LIMIT_STORAGE_URL is not asynchronous: {type(storage)}")
    return storage


# Scope for requests that match no route. They still need a counter — an unknown path is the
# cheapest thing to flood — but they must share one, or a scan of random URLs would create an
# unbounded number of keys in Redis.
_UNMATCHED_ROUTE_SCOPE = "unmatched"


def route_scope(request: Request) -> str:
    """The counter scope for a request: the route **pattern**, not the raw path.

    Keying on the raw path would let anyone create as many Redis keys as they can invent URLs —
    the limiter would become the memory-exhaustion vector. A pattern (`/api/items/{item_id}`)
    is bounded by the size of the route table.

    Middleware runs before routing, so the route is not in the scope yet; we ask the router
    ourselves. A partial match (right path, wrong method) counts as the same scope: a 405 flood
    is still a flood.
    """
    for route in request.scope["app"].routes:
        match, _ = route.matches(request.scope)
        if match is not Match.NONE:
            return str(getattr(route, "path_format", None) or getattr(route, "path", ""))
    return _UNMATCHED_ROUTE_SCOPE


def client_key(request: Request, *, trusted_proxy_hops: int = 0) -> str:
    """The client address as the counter key. All the difficulty sits in `X-Forwarded-For`.

    The header is fully controlled by the client, and proxies only **append** to its end. So we
    count from the right: with one proxy the real address is the last entry, with two it is the
    second to last. Entries to their left could have been made up by the client and are ignored.

    `trusted_proxy_hops=0` (the default) means "the application faces the client directly" and
    the header is then **ignored entirely**. That is the safe default: trusting the header with
    no proxy in front would let anyone get a fresh counter bucket simply by writing a random
    address, i.e. the limit would cease to exist.

    The value is validated as an IP address — otherwise a client injects arbitrary text into
    Redis keys (unbounded cardinality, unbounded key length).
    """
    peer = request.client.host if request.client else _UNKNOWN_CLIENT
    if trusted_proxy_hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if len(entries) < trusted_proxy_hops:
        # A chain shorter than the configuration claims: either somebody bypassed the proxy or
        # the configuration is wrong. In both cases we trust only what we can see ourselves.
        logger.warning(
            "X-Forwarded-For has %d entries with %d trusted proxies — using the peer address",
            len(entries),
            trusted_proxy_hops,
        )
        return peer

    candidate = entries[-trusted_proxy_hops]
    try:
        ip_address(candidate)
    except ValueError:
        logger.warning("X-Forwarded-For holds no IP address at the expected position")
        return peer
    return candidate


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        rules: tuple[RateLimitRule, ...],
        storage: Storage | None = None,
        exempt_paths: frozenset[str] = RATE_LIMIT_EXEMPT_PATHS,
        trusted_proxy_hops: int = 0,
    ) -> None:
        super().__init__(app)
        self._rules = rules
        self._exempt_paths = exempt_paths
        self._trusted_proxy_hops = trusted_proxy_hops
        self._limiter = MovingWindowRateLimiter(storage or MemoryStorage())
        # Emergency counter in process memory. Used when shared storage dies: the limit then
        # becomes per instance instead of global, but it does NOT disappear.
        self._fallback = MovingWindowRateLimiter(MemoryStorage())

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Preflight never touches the application and must pass, otherwise the browser reports
        # a CORS error instead of a 429.
        if request.method == "OPTIONS" or request.url.path in self._exempt_paths:
            return await call_next(request)

        rule = next((r for r in self._rules if r.matches(request.method, request.url.path)), None)
        if rule is None:
            return await call_next(request)

        key = client_key(request, trusted_proxy_hops=self._trusted_proxy_hops)
        scope = route_scope(request) if rule.per_route else rule.name
        limiter = self._limiter
        try:
            within_limit = await limiter.hit(rule.item, rule.name, scope, key)
        except Exception:
            # Degradation, not fail-open. A dead Redis must not block traffic, but "let
            # everything through" would mean one `redis-cli SHUTDOWN` removes the login limit.
            # So we fall back to a counter in process memory: with N replicas the budget grows
            # N-fold, but brute force still hits a wall.
            logger.exception("rate limit storage unavailable — counting in process memory")
            limiter = self._fallback
            within_limit = await limiter.hit(rule.item, rule.name, scope, key)

        if not within_limit:
            return await self._too_many_requests(limiter, rule, scope, key)
        return await call_next(request)

    async def _too_many_requests(
        self, limiter: MovingWindowRateLimiter, rule: RateLimitRule, scope: str, key: str
    ) -> JSONResponse:
        stats = await limiter.get_window_stats(rule.item, rule.name, scope, key)
        retry_after = max(1, int(stats.reset_time - time.time()))
        response = error_response(
            429, ApiError.RATE_LIMITED, "Too many requests. Please try again shortly."
        )
        # Sent on the rejection only, not on every response. The remaining budget is a second
        # round trip to the storage, and paying it on every successful request to inform a
        # client that is nowhere near the limit is the wrong trade. A client that has just been
        # told "no" gets the full picture.
        response.headers["Retry-After"] = str(retry_after)
        response.headers["X-RateLimit-Limit"] = str(rule.item.amount)
        response.headers["X-RateLimit-Remaining"] = str(max(0, stats.remaining))
        response.headers["X-RateLimit-Reset"] = str(int(stats.reset_time))
        return response
