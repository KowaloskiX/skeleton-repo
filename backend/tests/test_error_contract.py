"""One error shape for the whole API — including failures the framework produces itself.

A client that has to recognize three response shapes depending on which layer rejected the
request will handle two of them and fall back to "something went wrong" on the third. These
tests pin the envelope: `code`, `message`, and a `request_id` matching the response header.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.domain.errors import ApiError
from app.core.observability import REQUEST_ID_HEADER
from app.db.client import Database
from app.main import create_app

type CsrfHeaders = Callable[[], dict[str, str]]

SECRET_IN_MESSAGE = "mongodb://app:hunter2@internal-host:27017"


def _assert_envelope(body: dict[str, Any], code: ApiError) -> None:
    assert body["code"] == code
    assert body["message"], "an error without a message forces the client to invent one"
    assert body["request_id"], "no request_id means a user report cannot be tied to a log line"


async def test_unknown_path_uses_the_error_envelope(client: AsyncClient) -> None:
    """FastAPI answers `{"detail": "Not Found"}` by default — a different shape from every
    other error in this API, so the client would fall back to a generic message."""
    response = await client.get("/api/no-such-resource")

    assert response.status_code == 404
    _assert_envelope(response.json(), ApiError.NOT_FOUND)


async def test_wrong_method_uses_the_envelope_and_keeps_allow(client: AsyncClient) -> None:
    """405 without an `Allow` header is not a valid HTTP 405 — the header has to survive the
    rewrite of the body."""
    response = await client.get("/api/auth/login")

    assert response.status_code == 405
    _assert_envelope(response.json(), ApiError.METHOD_NOT_ALLOWED)
    assert "allow" in response.headers


async def test_validation_error_keeps_field_detail_and_gains_the_envelope(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    """The field-level `detail` is what the form needs; the envelope is what the generic error
    handler needs. Both, not one or the other."""
    response = await client.post("/api/auth/login", json={"email": "not-an-email"}, headers=csrf())

    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, ApiError.VALIDATION_FAILED)
    assert isinstance(body["detail"], list) and body["detail"], "field errors disappeared"


async def test_request_id_in_the_body_matches_the_header(client: AsyncClient) -> None:
    """The point of putting it in the body: a user reads it off the screen, support greps the
    logs for it. A different value in each place would defeat that."""
    response = await client.get("/api/no-such-resource")

    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]


@pytest.fixture
async def crashing_client(settings: Settings, database: Database) -> AsyncClient:
    """An application with a route that raises. `raise_app_exceptions=False` makes the
    transport behave like a real server: it returns the handler's response instead of
    re-raising into the test."""
    application: FastAPI = create_app(settings)
    application.state.database = database
    application.dependency_overrides[get_settings] = lambda: settings

    @application.get("/api/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError(f"connection failed: {SECRET_IN_MESSAGE}")

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_unhandled_exception_returns_json_not_plain_text(
    crashing_client: AsyncClient,
) -> None:
    """Starlette's default 500 is `text/plain`, so a client parsing JSON gets a parse error on
    top of the original failure."""
    async with crashing_client as client:
        response = await client.get("/api/boom")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    _assert_envelope(response.json(), ApiError.INTERNAL_ERROR)


async def test_unhandled_exception_does_not_leak_its_message(
    crashing_client: AsyncClient,
) -> None:
    """Exception text tends to carry connection strings and internal paths. It belongs in the
    log, not in a response an anonymous caller can trigger."""
    async with crashing_client as client:
        response = await client.get("/api/boom")

    assert SECRET_IN_MESSAGE not in response.text
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


async def test_middleware_rejections_share_the_same_envelope(client: AsyncClient) -> None:
    """A 403 from CSRF is produced by middleware, far from the exception handlers — it still
    has to look like every other error."""
    response = await client.post("/api/auth/logout", json={})

    assert response.status_code == 403
    _assert_envelope(response.json(), ApiError.CSRF_INVALID)


async def test_api_never_exposes_the_database_identifier_type(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    """Identifiers cross the boundary as strings, and the schema says exactly that.

    The point is not cosmetic. If `ObjectId` reached the contract, the generated TS client would
    carry the shape of whichever database is underneath, and replacing it would break every
    consumer. `app.db.identifiers` is the only place that knows the real type.
    """
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "identifiers@example.com",
            "password": "correct-horse-battery-staple",
            "organization_name": "Identifier Org",
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text

    body = response.json()
    for identifier in (body["id"], body["organizations"][0]["id"]):
        assert isinstance(identifier, str), "an identifier must serialize as a string"
        assert len(identifier) == 24, "an ObjectId is 24 hex characters"
        int(identifier, 16)  # raises if it is not hex, which would mean a different id type
