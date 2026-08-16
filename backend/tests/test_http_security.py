"""The HTTP edge: headers, body limit, CSRF default-deny, the docs gate.

None of these mechanisms has a visible effect on the happy path — which is exactly why they
are easy to delete during a refactor and never notice. Each has a test here that turns red
when the middleware disappears from `create_app`.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.config import Settings, get_settings
from app.core.csrf import issue_csrf_token
from app.core.domain.errors import ApiError
from app.core.http_security import CSRF_HEADER_NAME
from app.db.client import Database
from app.main import create_app

# A test constant, not a secret: the validator only checks the length, so a repeated
# character satisfies it without looking like a credential.
STRONG_SECRET = "a" * 32
SMALL_BODY_LIMIT = 1024


def _client_for(application: FastAPI) -> AsyncClient:
    """A client without a lifespan — these tests stop at the middleware, no database needed."""
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


@pytest.fixture
def tls_app() -> FastAPI:
    """An application configured like production: HTTPS, strong secret, docs disabled."""
    return create_app(Settings(app_env="prod", auth_secret=STRONG_SECRET))


@pytest.fixture
async def limited_client(settings: Settings, database: Database) -> AsyncIterator[AsyncClient]:
    """An application with a tight body limit — 1 MB in a test is needless seconds.

    With a real database, because one of the tests has to reach the route and check that the
    body survived the trip through the middleware.
    """
    limited = settings.model_copy(update={"max_request_body_bytes": SMALL_BODY_LIMIT})
    application = create_app(limited)
    application.state.database = database
    application.dependency_overrides[get_settings] = lambda: limited
    async with _client_for(application) as http_client:
        yield http_client


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/auth/session",
        "/api/nie-ma-takiej-trasy",  # a 404 is a response too, and it also reaches the browser
    ],
)
async def test_security_headers_are_on_every_response(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    headers = response.headers

    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "object-src 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["permissions-policy"]


async def test_hsts_is_sent_only_over_tls(client: AsyncClient, tls_app: FastAPI) -> None:
    """HSTS sent from a dev machine pins `localhost` to HTTPS in the developer's browser —
    for a year, with no easy undo."""
    assert "strict-transport-security" not in (await client.get("/api/health")).headers

    async with _client_for(tls_app) as tls_client:
        response = await tls_client.get("/api/health")
    assert "max-age=31536000" in response.headers["strict-transport-security"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_api_docs_are_closed_outside_local(
    client: AsyncClient, tls_app: FastAPI, path: str
) -> None:
    assert (await client.get(path)).status_code == 200, "Swagger must work locally"

    async with _client_for(tls_app) as tls_client:
        assert (await tls_client.get(path)).status_code == 404


async def test_oversized_declared_body_is_rejected(limited_client: AsyncClient) -> None:
    """Rejected on `Content-Length`, i.e. before FastAPI buffers the body in memory."""
    response = await limited_client.post("/api/auth/login", content=b"x" * (SMALL_BODY_LIMIT + 1))
    assert response.status_code == 413
    assert response.json()["code"] == ApiError.PAYLOAD_TOO_LARGE


async def test_oversized_chunked_body_is_rejected(
    limited_client: AsyncClient, settings: Settings
) -> None:
    """Without `Content-Length` there is no declaration — we count bytes on the fly.

    Otherwise the limit is bypassed with one flag: `curl -H 'Transfer-Encoding: chunked'`.
    A CSRF token is needed because the counter reacts once the application reads the stream.
    """
    await limited_client.get("/api/auth/session")
    token = limited_client.cookies.get(settings.effective_csrf_cookie_name)
    assert token is not None

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(4):
            yield b"x" * SMALL_BODY_LIMIT

    response = await limited_client.post(
        "/api/auth/login",
        content=chunks(),
        headers={CSRF_HEADER_NAME: token, "content-type": "application/json"},
    )
    assert response.status_code == 413


async def test_body_under_limit_still_reaches_the_application(
    limited_client: AsyncClient, settings: Settings
) -> None:
    """Positive control: the middleware reads the stream, so it must pass it on untouched.

    Without this test "the limit works" would also cover "every chunked request gets an empty
    body" — and that only shows up in production. So the request has to reach the route rather
    than bounce off CSRF earlier.
    """
    await limited_client.get("/api/auth/session")
    token = limited_client.cookies.get(settings.effective_csrf_cookie_name)
    assert token is not None

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"email": "kto@example.com", "password": "correct-horse-battery"}'

    response = await limited_client.post(
        "/api/auth/login",
        content=chunks(),
        headers={CSRF_HEADER_NAME: token, "content-type": "application/json"},
    )
    # 401 = the route received complete data and rejected an unknown user.
    # 422 would mean the body arrived empty, i.e. the middleware ate the stream.
    assert response.status_code == 401, response.text


async def test_csrf_is_default_deny_on_unknown_route(client: AsyncClient) -> None:
    """403, not 404 — proof that the protection lives in middleware, ahead of routing.

    Had it lived in a route's `dependencies=[...]`, the first endpoint added without that line
    would ship unprotected while CI stayed green.
    """
    response = await client.post("/api/nie-ma-takiej-trasy", json={})
    assert response.status_code == 403
    assert response.json()["code"] == ApiError.CSRF_INVALID


async def test_unsigned_token_is_rejected(client: AsyncClient, settings: Settings) -> None:
    """Plain double-submit would let this through: cookie == header, but with no signature."""
    client.cookies.set(settings.effective_csrf_cookie_name, "value-without-signature")
    response = await client.post(
        "/api/auth/login", json={}, headers={CSRF_HEADER_NAME: "value-without-signature"}
    )
    assert response.status_code == 403


async def test_token_bound_to_another_session_is_rejected(
    client: AsyncClient, settings: Settings
) -> None:
    """The point of the signature: the attacker holds their OWN, correctly signed token from
    their own account and plants it on the victim through a hijacked subdomain. Session
    binding stops that."""
    attacker_token = issue_csrf_token(settings.auth_secret, "attacker-session")
    client.cookies.set(settings.effective_csrf_cookie_name, attacker_token)
    client.cookies.set(settings.session_cookie_name, "victim-session")

    response = await client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: attacker_token})
    assert response.status_code == 403


async def test_token_bound_to_own_session_passes_csrf(
    client: AsyncClient, settings: Settings
) -> None:
    """Positive control for the test above: the same request shape, a matching binding.

    401 (unknown session) instead of 403 — CSRF let it through and authorization rejected it.
    """
    own_token = issue_csrf_token(settings.auth_secret, "victim-session")
    client.cookies.set(settings.effective_csrf_cookie_name, own_token)
    client.cookies.set(settings.session_cookie_name, "victim-session")

    response = await client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: own_token})
    assert response.status_code == 401, response.text


async def test_csrf_cookie_is_readable_by_javascript_but_session_is_not(
    client: AsyncClient, settings: Settings
) -> None:
    """The asymmetry is intended: the CSRF token has to be echoable in a header by JavaScript,
    the session credential never. The signature defends the token, `HttpOnly` the session."""
    response = await client.get("/api/auth/session")
    csrf_cookie = next(
        c
        for c in response.headers.get_list("set-cookie")
        if c.startswith(f"{settings.effective_csrf_cookie_name}=")
    )
    assert "httponly" not in csrf_cookie.lower()


def _csrf_cookie_value(response: Response, settings: Settings) -> str | None:
    """Reads the cookie from the response header rather than from the client jar.

    The httpx jar can hold two entries under the same name (different domain/path) and the
    read then raises `CookieConflict` — but the test is about the application, not the client.
    """
    prefix = f"{settings.effective_csrf_cookie_name}="
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(prefix):
            return header.removeprefix(prefix).split(";", 1)[0]
    return None


async def test_stale_csrf_token_is_replaced_on_the_next_session_read(
    client: AsyncClient, settings: Settings
) -> None:
    """The token is bound to the session, so once that expires it stops passing.

    Without replacement the application hits a dead end: EVERY mutation gets a 403, and signing
    in again is a mutation too. The only way out would be clearing cookies by hand.
    """
    stale = issue_csrf_token(settings.auth_secret, "a-session-that-no-longer-exists")
    client.cookies.set(settings.effective_csrf_cookie_name, stale, domain="test", path="/")

    replaced = _csrf_cookie_value(await client.get("/api/auth/session"), settings)

    assert replaced is not None, "a stale CSRF token must be replaced"
    assert replaced != stale

    # And the new token really works — 401 (no session) rather than 403 (a CSRF bounce).
    client.cookies.set(settings.effective_csrf_cookie_name, replaced, domain="test", path="/")
    response = await client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: replaced})
    assert response.status_code == 401, response.text


async def test_valid_csrf_token_is_not_rotated_on_every_read(
    client: AsyncClient, settings: Settings
) -> None:
    """Negative control: rotating on every GET would break concurrent requests — one would
    overwrite the cookie while the other flew with the old value."""
    first = _csrf_cookie_value(await client.get("/api/auth/session"), settings)
    assert first is not None

    assert _csrf_cookie_value(await client.get("/api/auth/session"), settings) is None, (
        "a valid token must not be reissued on every session read"
    )
