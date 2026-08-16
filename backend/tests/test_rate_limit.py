"""Rate limiting — verified by behaviour, not by the presence of a decorator.

The application receives tiny limits here through injected `Settings`, so the tests are fast
and deterministic instead of depending on production values.
"""

import re
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from limits import parse
from limits.aio.storage import MemoryStorage
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.rate_limit import (
    RateLimitMiddleware,
    RateLimitRule,
    build_rate_limit_rules,
    client_key,
)
from app.db.client import Database
from app.main import create_app
from app.routes.dependencies import CSRF_HEADER_NAME

GLOBAL_LIMIT = 3
LOGIN_LIMIT = 2


@pytest.fixture
def tight_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "global_rate_limit": f"{GLOBAL_LIMIT}/minute",
            "login_rate_limit": f"{LOGIN_LIMIT}/minute",
        }
    )


@pytest.fixture
async def tight_client(tight_settings: Settings, database: Database) -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app(tight_settings)
    app.state.database = database
    app.dependency_overrides[get_settings] = lambda: tight_settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def test_last_rule_is_catch_all(settings: Settings) -> None:
    """The rule structure guarantees coverage: a new endpoint cannot ship unlimited."""
    rules = build_rate_limit_rules(settings)
    catch_all = rules[-1]
    assert catch_all.methods is None
    assert catch_all.matches("PATCH", "/api/any/new/route")


async def test_global_limit_covers_endpoint_without_own_rule(
    tight_client: AsyncClient,
) -> None:
    for _ in range(GLOBAL_LIMIT):
        assert (await tight_client.get("/api/auth/session")).status_code == 200

    blocked = await tight_client.get("/api/auth/session")
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1


async def test_health_is_exempt(tight_client: AsyncClient) -> None:
    """A liveness probe must not be throttled — the orchestrator would read it as an outage."""
    for _ in range(GLOBAL_LIMIT * 3):
        assert (await tight_client.get("/api/health")).status_code == 200


async def test_auth_write_limit_is_separate_and_stricter(
    tight_client: AsyncClient, tight_settings: Settings
) -> None:
    await tight_client.get("/api/auth/session")  # issues the CSRF cookie
    headers = {CSRF_HEADER_NAME: tight_client.cookies[tight_settings.csrf_cookie_name]}
    payload = {"email": "nobody@example.com", "password": "correct-horse-battery-staple"}

    for _ in range(LOGIN_LIMIT):
        response = await tight_client.post("/api/auth/login", json=payload, headers=headers)
        assert response.status_code == 401, response.text

    assert (
        await tight_client.post("/api/auth/login", json=payload, headers=headers)
    ).status_code == 429


async def test_rejected_requests_are_counted(tight_client: AsyncClient) -> None:
    """The point of our own middleware: the limit runs BEFORE dependencies, so floods bounced
    by CSRF (403) or a missing session (401) consume budget too.

    The slowapi decorator counted only after dependencies and let those requests through
    unlimited.
    """
    for _ in range(LOGIN_LIMIT):
        # No CSRF header -> 403 from the middleware, but the request was already counted.
        assert (await tight_client.post("/api/auth/login", json={})).status_code == 403

    assert (await tight_client.post("/api/auth/login", json={})).status_code == 429


async def test_limits_are_per_client_ip(tight_client: AsyncClient) -> None:
    for _ in range(GLOBAL_LIMIT):
        assert (await tight_client.get("/api/auth/session")).status_code == 200
    assert (await tight_client.get("/api/auth/session")).status_code == 429

    # `X-Forwarded-For` is NOT taken into account without declared proxies — otherwise anyone
    # could bypass the limit with a single header.
    spoofed = await tight_client.get("/api/auth/session", headers={"X-Forwarded-For": "9.9.9.9"})
    assert spoofed.status_code == 429


class _BrokenStorage(MemoryStorage):
    """Storage that always fails — impersonates an unreachable Redis."""

    async def acquire_entry(self, *args: object, **kwargs: object) -> bool:
        raise ConnectionError("redis is down")


def _request_from(client_host: str | None, forwarded: str | None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (client_host, 1234) if client_host else None,
        }
    )


def test_forwarded_header_is_ignored_without_declared_proxies() -> None:
    """The safe default. If the header counted with no proxy in front, anyone could get a
    fresh counter bucket by writing a random address — i.e. there would be no limit."""
    request = _request_from("10.0.0.1", "1.2.3.4")
    assert client_key(request) == "10.0.0.1"


def test_only_the_entry_added_by_our_proxy_is_trusted() -> None:
    """A proxy **appends** to the end, so entries on the left come from the client.

    An attacker sends `X-Forwarded-For: <random address>` and nginx appends their real one —
    counting from the left would hand them a new bucket on every request.
    """
    request = _request_from("10.0.0.1", "9.9.9.9, 203.0.113.7")
    assert client_key(request, trusted_proxy_hops=1) == "203.0.113.7"
    # Two of our own proxies: the real address is one entry earlier.
    assert client_key(request, trusted_proxy_hops=2) == "9.9.9.9"


@pytest.mark.parametrize(
    "forwarded",
    [
        "not-an-address",  # text instead of an IP — would land in Redis as a key
        "203.0.113.7",  # a chain shorter than the configuration declares
        None,
    ],
)
def test_unusable_forwarded_header_falls_back_to_peer(forwarded: str | None) -> None:
    request = _request_from("10.0.0.1", forwarded)
    assert client_key(request, trusted_proxy_hops=2) == "10.0.0.1"


async def test_limit_survives_storage_outage() -> None:
    """A dead Redis degrades the counter to process memory but does NOT switch it off.

    Fail-open would mean one `redis-cli SHUTDOWN` removes the login limit.
    """
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(
            RateLimitRule(
                name="test", methods=None, path=re.compile(r".*"), item=parse("2/minute")
            ),
        ),
        storage=_BrokenStorage(),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = [(await client.get("/ping")).status_code for _ in range(3)]

    assert statuses == [200, 200, 429], statuses


async def test_one_endpoint_does_not_spend_the_budget_of_another(
    tight_client: AsyncClient,
) -> None:
    """A general ceiling should limit a client per endpoint, not across the whole API.

    With one shared counter, somebody hammering a single route locks the caller out of every
    other one — including routes they were using legitimately.
    """
    for _ in range(GLOBAL_LIMIT):
        assert (await tight_client.get("/api/auth/session")).status_code == 200
    assert (await tight_client.get("/api/auth/session")).status_code == 429

    # A different route still has its own budget.
    assert (await tight_client.get("/api/no-such-route")).status_code == 404


async def test_login_and_register_share_one_budget(
    tight_client: AsyncClient, tight_settings: Settings
) -> None:
    """Deliberately NOT per route: an attacker alternating between the two endpoints would
    otherwise get twice the attempts."""
    await tight_client.get("/api/auth/session")
    headers = {CSRF_HEADER_NAME: tight_client.cookies[tight_settings.csrf_cookie_name]}

    for _ in range(LOGIN_LIMIT):
        response = await tight_client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "correct-horse-battery-staple"},
            headers=headers,
        )
        assert response.status_code == 401, response.text

    blocked = await tight_client.post(
        "/api/auth/register",
        json={
            "email": "someone@example.com",
            "password": "correct-horse-battery-staple",
            "organization_name": "Some Org",
        },
        headers=headers,
    )
    assert blocked.status_code == 429, "registration must not refill the login budget"


async def test_unknown_paths_share_a_single_counter(tight_client: AsyncClient) -> None:
    """Keying on the raw path would let anyone create as many storage keys as they can invent
    URLs — the limiter would become the memory-exhaustion vector it exists to prevent."""
    for index in range(GLOBAL_LIMIT):
        assert (await tight_client.get(f"/api/does-not-exist-{index}")).status_code == 404

    assert (await tight_client.get("/api/yet-another-unknown")).status_code == 429


async def test_rejection_tells_the_client_how_long_to_wait(tight_client: AsyncClient) -> None:
    for _ in range(GLOBAL_LIMIT):
        await tight_client.get("/api/auth/session")

    blocked = await tight_client.get("/api/auth/session")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert int(blocked.headers["x-ratelimit-limit"]) == GLOBAL_LIMIT
    assert int(blocked.headers["x-ratelimit-remaining"]) == 0
    assert int(blocked.headers["x-ratelimit-reset"]) > 0
