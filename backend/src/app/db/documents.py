"""Document base: shared fields and mixins.

Identifiers are Beanie's default **`ObjectId`**, not UUID. Two reasons that matter at volume:
12 bytes instead of 16 on every document and on every index referencing one, and the leading
4-byte timestamp, which turns the `_id` index into a creation-time index for free — a collection
growing with traffic needs no separate index to page through it in order.

The cost is deliberate and paid at one boundary: `ObjectId` lives in `bson`, which the domain
layer must not import (`domain_agnostic` in `.importlinter`), so identifiers cross into the
domain and into the API as strings. `app.db.identifiers` owns that conversion, and it is the
only place that knows the database's id type.
"""

from datetime import UTC, datetime

from beanie import PydanticObjectId
from pydantic import Field


def utc_now() -> datetime:
    """One place for "now" — easier to swap in tests than scattered `datetime.now` calls."""
    return datetime.now(UTC)


class TimestampMixin:
    # `created_at` stays a field even though `_id` already encodes the creation time: the
    # timestamp inside an ObjectId has second resolution and belongs to the driver, while this
    # one is ours and is what the API exposes.
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TenantOwnedMixin:
    """The document belongs to an organization.

    Mongo has neither foreign keys nor cascades, so tenant isolation and cleanup of related data
    are a matter of discipline: read through `TenantScopedRepository`, delete explicitly in the
    service. Enforced by `tests/test_tenancy_contract.py`.
    """

    organization_id: PydanticObjectId
