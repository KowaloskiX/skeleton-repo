"""Multi-tenancy and index contract — enforced by tests, not merely by convention.

Mongo has no foreign keys, no cascades and no Row-Level Security, so tenant isolation and
integrity rest entirely on code discipline and indexes. These tests are that safety net:
a new collection cannot enter the repository without a deliberate decision.

Assertions run against the **live database** rather than class declarations — we check that
the indexes really exist after `init_beanie`, not just that somebody described them.
"""

from collections.abc import Mapping
from typing import Any

from app.db.client import Database
from app.db.documents import TenantOwnedMixin
from app.documents import DOCUMENT_MODELS

# Collections that are deliberately NOT tenant-owned. Adding anything here is a decision, not
# an accident: such a document is visible across organization boundaries.
TENANT_EXEMPT_COLLECTIONS = frozenset(
    {
        "users",  # a user can belong to many organizations
        "user_sessions",  # a session belongs to a user, not to an organization
        "organizations",  # the tenant itself
    }
)


def _collection_name(model: type[Any]) -> str:
    return str(model.get_settings().name)


def _indexed_fields(index_information: Mapping[str, Any]) -> set[str]:
    return {field for index in index_information.values() for field, _ in index["key"]}


def test_every_collection_is_either_tenant_owned_or_explicitly_exempt() -> None:
    for model in DOCUMENT_MODELS:
        name = _collection_name(model)
        assert issubclass(model, TenantOwnedMixin) or name in TENANT_EXEMPT_COLLECTIONS, (
            f"Collection '{name}' has no organization_id and is not on the exemption list. "
            "Add TenantOwnedMixin or list it in TENANT_EXEMPT_COLLECTIONS with a reason."
        )


def test_exempt_list_has_no_stale_entries() -> None:
    existing = {_collection_name(model) for model in DOCUMENT_MODELS}
    assert existing >= TENANT_EXEMPT_COLLECTIONS, (
        "the exemption list points at collections that do not exist"
    )


async def test_tenant_owned_collections_index_organization_id(database: Database) -> None:
    """Without an index every tenant query scans the whole collection."""
    tenant_owned = [m for m in DOCUMENT_MODELS if issubclass(m, TenantOwnedMixin)]
    assert tenant_owned, "no tenant-owned collection — the contract would be meaningless"

    for model in tenant_owned:
        name = _collection_name(model)
        fields = _indexed_fields(await database.database[name].index_information())
        assert "organization_id" in fields, f"organization_id in '{name}' must be indexed"


async def test_unique_constraints_exist_in_database(database: Database) -> None:
    """Uniqueness is the only defence against duplicates — Mongo has neither FKs nor CHECKs."""
    expected_unique = {
        "users": [("email", 1)],
        "user_sessions": [("token_hash", 1)],
        "organizations": [("slug", 1)],
        "memberships": [("user_id", 1), ("organization_id", 1)],
    }
    for collection, key in expected_unique.items():
        indexes = await database.database[collection].index_information()
        unique_keys = [
            [tuple(part) for part in index["key"]]
            for index in indexes.values()
            if index.get("unique")
        ]
        assert key in unique_keys, f"'{collection}' needs a unique index on {key}"


async def test_sessions_expire_automatically(database: Database) -> None:
    """The TTL index replaces a cleanup job for expired sessions."""
    indexes = await database.database["user_sessions"].index_information()
    ttl = [i for i in indexes.values() if "expireAfterSeconds" in i]
    assert ttl, "user_sessions needs a TTL index on expires_at"
    assert [tuple(part) for part in ttl[0]["key"]] == [("expires_at", 1)]
