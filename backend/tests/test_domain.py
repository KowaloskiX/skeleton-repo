"""Unit tests for the pure domain — no database, no HTTP."""

import pytest
from beanie import PydanticObjectId

from app.core.domain.identity import AuthenticatedUser, OrganizationRef
from app.core.domain.roles import Role
from app.core.domain.slug import slugify


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Acme Sp. z o.o.", "acme-sp-z-o-o"),
        ("  Trailing  ", "trailing"),
        # Non-ASCII characters drop out; the fallback beats an empty slug.
        ("\u017b\u00d3\u0141\u0106", "org"),
        ("a" * 80, "a" * 48),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


def test_role_in_returns_none_for_foreign_organization() -> None:
    # Strings, not the database identifier type: the domain must not import `bson`, which is
    # exactly why `app.db.identifiers` converts at the persistence boundary.
    org_id = str(PydanticObjectId())
    user = AuthenticatedUser(
        id=str(PydanticObjectId()),
        email="owner@example.com",
        organizations=(OrganizationRef(id=org_id, name="Acme", slug="acme", role=Role.OWNER),),
    )
    assert user.role_in(org_id) == Role.OWNER
    assert user.role_in(str(PydanticObjectId())) is None
