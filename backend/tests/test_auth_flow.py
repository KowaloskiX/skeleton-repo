"""The money path: registration -> session -> sign-out -> sign-in."""

from collections.abc import Callable

from httpx import AsyncClient

from app.core.config import Settings
from app.core.domain.errors import AuthError
from app.core.domain.roles import Role

EMAIL = "Owner@Example.COM"
PASSWORD = "correct-horse-battery-staple"

type CsrfHeaders = Callable[[], dict[str, str]]


async def _register(client: AsyncClient, csrf: CsrfHeaders, email: str = EMAIL) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "organization_name": "Acme Ltd."},
        headers=csrf(),
    )
    assert response.status_code == 201, response.text


async def test_register_creates_owner_membership_and_session(
    client: AsyncClient, csrf: CsrfHeaders, settings: Settings
) -> None:
    await _register(client, csrf)

    session = (await client.get("/api/auth/session")).json()
    assert session["user"]["email"] == EMAIL.lower(), "the email must be normalized"
    assert session["user"]["organizations"][0]["role"] == Role.OWNER
    assert session["user"]["organizations"][0]["slug"] == "acme-ltd"
    assert client.cookies.get(settings.session_cookie_name) is not None


async def test_session_cookie_is_httponly_and_samesite_lax(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "organization_name": "Acme"},
        headers=csrf(),
    )
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("session="))
    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()


async def test_csrf_token_rotates_on_login(
    client: AsyncClient, csrf: CsrfHeaders, settings: Settings
) -> None:
    """Rotation on a privilege change — session fixation defence."""
    before = client.cookies.get(settings.csrf_cookie_name)
    await _register(client, csrf)
    assert client.cookies.get(settings.csrf_cookie_name) != before


async def test_duplicate_email_is_rejected(client: AsyncClient, csrf: CsrfHeaders) -> None:
    await _register(client, csrf)
    response = await client.post(
        "/api/auth/register",
        json={"email": EMAIL.lower(), "password": PASSWORD, "organization_name": "Another"},
        headers=csrf(),
    )
    assert response.status_code == 409
    assert response.json()["code"] == AuthError.EMAIL_TAKEN


async def test_login_after_logout(client: AsyncClient, csrf: CsrfHeaders) -> None:
    await _register(client, csrf)

    logout = await client.post("/api/auth/logout", headers=csrf())
    assert logout.status_code == 200
    assert (await client.get("/api/auth/session")).json()["user"] is None

    login = await client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers=csrf(),
    )
    assert login.status_code == 200, login.text
    assert login.json()["email"] == EMAIL.lower()


async def test_logout_keeps_csrf_cookie_usable(
    client: AsyncClient, csrf: CsrfHeaders, settings: Settings
) -> None:
    """After signing out the login form must work without an extra round trip."""
    await _register(client, csrf)
    await client.post("/api/auth/logout", headers=csrf())
    assert client.cookies.get(settings.csrf_cookie_name) is not None


async def test_logout_invalidates_session_server_side(
    client: AsyncClient, csrf: CsrfHeaders, settings: Settings
) -> None:
    """Server-side sessions mean instant revocation. The old cookie has to be dead."""
    await _register(client, csrf)
    stolen_token = client.cookies.get(settings.session_cookie_name)
    assert stolen_token is not None

    await client.post("/api/auth/logout", headers=csrf())
    client.cookies.set(settings.session_cookie_name, stolen_token)
    assert (await client.get("/api/auth/session")).json()["user"] is None


async def test_wrong_password_is_generic_401(client: AsyncClient, csrf: CsrfHeaders) -> None:
    await _register(client, csrf)
    response = await client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": "wrong-password-entirely"},
        headers=csrf(),
    )
    assert response.status_code == 401
    assert response.json()["code"] == AuthError.INVALID_CREDENTIALS


async def test_unknown_email_returns_same_error_as_wrong_password(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    """Anti-enumeration: a non-existent account must not be identifiable from the response."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": PASSWORD},
        headers=csrf(),
    )
    assert response.status_code == 401
    assert response.json()["code"] == AuthError.INVALID_CREDENTIALS


async def test_missing_csrf_header_is_rejected(client: AsyncClient) -> None:
    await client.get("/api/auth/session")  # sets the CSRF cookie
    response = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 403


async def test_mismatched_csrf_header_is_rejected(client: AsyncClient) -> None:
    await client.get("/api/auth/session")
    response = await client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-CSRF-Token": "forged-token"},
    )
    assert response.status_code == 403


async def test_logout_without_session_is_401(client: AsyncClient, csrf: CsrfHeaders) -> None:
    response = await client.post("/api/auth/logout", headers=csrf())
    assert response.status_code == 401


async def test_short_password_is_rejected_by_validation(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "abc", "organization_name": "X Y"},
        headers=csrf(),
    )
    assert response.status_code == 422


async def test_stale_session_cookie_is_ignored(
    client: AsyncClient, csrf: CsrfHeaders, settings: Settings
) -> None:
    await _register(client, csrf)
    client.cookies.set(settings.session_cookie_name, "fabricated-token")
    assert (await client.get("/api/auth/session")).json()["user"] is None


async def test_two_organizations_get_distinct_slugs(client: AsyncClient, csrf: CsrfHeaders) -> None:
    await _register(client, csrf, email="first@example.com")
    await client.post("/api/auth/logout", headers=csrf())
    await _register(client, csrf, email="second@example.com")

    session = (await client.get("/api/auth/session")).json()
    assert session["user"]["organizations"][0]["slug"] != "acme-ltd"


async def test_non_ascii_csrf_header_is_rejected_not_crashed(client: AsyncClient) -> None:
    """A header with a byte >= 0x80 must produce 403, not 500.

    `secrets.compare_digest` on strings requires ASCII, and Starlette decodes headers as
    latin-1 — so an anonymous user with one curl produced a 500 with a traceback and made
    monitoring confuse an attack with an application failure.
    """
    await client.get("/api/auth/session")
    # Raw bytes rather than str: httpx will not send non-ASCII as a string, but an attacker
    # sends bytes on the wire and Starlette decodes headers as latin-1.
    response = await client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers=[(b"x-csrf-token", b"\xe9")],
    )
    assert response.status_code == 403, response.text


async def test_validation_error_does_not_echo_submitted_password(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    """Pydantic puts the raw field value into `input` — i.e. the password into the 422 body.

    From there it would travel into proxy logs, Sentry and HAR files sent to support.
    """
    secret = "short-but-real"[:8]
    response = await client.post(
        "/api/auth/register",
        json={"email": "leak@example.com", "password": secret, "organization_name": "Leak Org"},
        headers=csrf(),
    )
    assert response.status_code == 422
    assert secret not in response.text, "the password came back in the validation response"
