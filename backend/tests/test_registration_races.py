"""Registration races and atomicity — the tests we pay for a replica set to run.

Three things invisible in happy-path tests that decide correctness: the check-then-insert
race, a slug collision and transaction rollback.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response

from app.core.config import Settings
from app.core.domain.errors import AuthError
from app.core.domain.result import Ok
from app.db.client import Database
from app.models.auth import User, UserSession
from app.models.organizations import Membership, Organization
from app.services.auth import AuthService

PASSWORD = "correct-horse-battery-staple"
type CsrfHeaders = Callable[[], dict[str, str]]


async def test_concurrent_registration_of_same_email_returns_conflict(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    """The "is this email taken" check is NOT a safeguard — the unique index is.

    Without handling `DuplicateKeyError` the second request ended in a 500 instead of a 409
    (measured).
    """
    payload = {
        "email": "race@example.com",
        "password": PASSWORD,
        "organization_name": "Race Org",
    }
    headers = csrf()
    responses = await asyncio.gather(
        client.post("/api/auth/register", json=payload, headers=headers),
        client.post("/api/auth/register", json=payload, headers=headers),
        return_exceptions=True,
    )

    settled: list[Response] = []
    for response in responses:
        assert isinstance(response, Response), (
            f"request ended with an unhandled exception: {response!r}"
        )
        settled.append(response)

    codes = sorted(response.status_code for response in settled)
    assert codes == [201, 409], f"expected 201 and 409, got {codes}"
    assert await User.find(User.email == "race@example.com").count() == 1


async def test_slug_collision_does_not_break_registration(
    client: AsyncClient, csrf: CsrfHeaders
) -> None:
    """Two organizations with the same name: the slugs must diverge, not break the write."""
    for index in range(2):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": f"same-name-{index}@example.com",
                "password": PASSWORD,
                "organization_name": "Identical Name",
            },
            headers=csrf(),
        )
        assert response.status_code == 201, response.text
        await client.post("/api/auth/logout", headers=csrf())

    slugs = {organization.slug for organization in await Organization.find().to_list(10)}
    assert len(slugs) == 2, f"slugs must be unique, got: {slugs}"


async def test_failed_registration_leaves_nothing_behind(
    database: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transaction rollback — the only reason we require a replica set.

    We force a failure on the third of four writes. Without a transaction the database would
    keep a user without an organization and an organization without an owner.
    """
    service = AuthService(database, settings)

    async def explode(*_: object, **__: object) -> None:
        raise RuntimeError("failure while writing the membership")

    monkeypatch.setattr(service.identity, "add_membership", explode)

    with pytest.raises(RuntimeError):
        await service.register(
            email="rollback@example.com", password=PASSWORD, organization_name="Rollback Org"
        )

    assert await User.find().count() == 0, "the user survived the rollback"
    assert await Organization.find().count() == 0, "the organization survived the rollback"
    assert await Membership.find().count() == 0
    assert await UserSession.find().count() == 0


async def test_successful_registration_writes_all_four_documents(
    database: Database, settings: Settings
) -> None:
    """Positive control for the rollback test: the happy path really does write everything."""
    service = AuthService(database, settings)
    result = await service.register(
        email="atomic@example.com", password=PASSWORD, organization_name="Atomic Org"
    )

    assert isinstance(result, Ok)
    assert await User.find().count() == 1
    assert await Organization.find().count() == 1
    assert await Membership.find().count() == 1
    assert await UserSession.find().count() == 1


async def test_expired_session_is_rejected(
    client: AsyncClient, csrf: CsrfHeaders, settings: Settings
) -> None:
    """A genuinely expired session, not a fabricated token.

    The TTL index deletes lazily (a pass roughly every 60 s), so correctness depends on the
    `expires_at > now` filter in the query. Without this test the regression would stay
    invisible until the first security audit.
    """
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "expired@example.com",
            "password": PASSWORD,
            "organization_name": "Expired Org",
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text
    assert (await client.get("/api/auth/session")).json()["user"] is not None

    user_session = await UserSession.find_one()
    assert user_session is not None
    await user_session.set({UserSession.expires_at: datetime.now(UTC) - timedelta(hours=1)})

    assert (await client.get("/api/auth/session")).json()["user"] is None, (
        "an expired session still works — check the expires_at filter in SessionRepository"
    )


async def test_duplicate_email_error_code_is_stable(client: AsyncClient, csrf: CsrfHeaders) -> None:
    """The error code is a contract for the frontend — it must not change during a refactor."""
    payload = {
        "email": "stable@example.com",
        "password": PASSWORD,
        "organization_name": "Stable Org",
    }
    assert (
        await client.post("/api/auth/register", json=payload, headers=csrf())
    ).status_code == 201
    conflict = await client.post("/api/auth/register", json=payload, headers=csrf())
    assert conflict.status_code == 409
    assert conflict.json()["code"] == AuthError.EMAIL_TAKEN
