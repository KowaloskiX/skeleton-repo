"""Shared repository mechanics: tenant isolation and result bounding.

Chosen multi-tenancy model: an `organization_id` field on the document plus a filter appended
here. Mongo has no equivalent of Row-Level Security, so this is the only protective layer —
which is why the filter lives in the base class rather than at call sites. Every document with
`TenantOwnedMixin` must be read through this repository; `tests/test_tenancy_contract.py`
enforces that.
"""

import logging
from typing import Any, Protocol

from beanie import PydanticObjectId

from app.db.documents import TenantOwnedMixin

logger = logging.getLogger(__name__)

# Default ceiling on documents returned by a single query. This is not "how much data we have"
# but "how much we are willing to pull into memory for one request". Above this threshold the
# response would need pagination anyway.
MAX_DOCUMENTS_PER_QUERY = 200


class _Listable[DocT](Protocol):
    async def to_list(self, length: int | None = None) -> list[DocT]: ...


async def bounded_to_list[DocT](
    query: _Listable[DocT], *, what: str, limit: int = MAX_DOCUMENTS_PER_QUERY
) -> list[DocT]:
    """`to_list()` with a ceiling — and **loudly** so when the ceiling is hit.

    Silent truncation would be a silent bug: a user with 201 organizations would stop seeing
    one of them and nobody would find out. So we fetch `limit + 1` and log an error when the
    threshold is exceeded — the response is trimmed, but the fact is visible in logs and can
    be alerted on.

    Unbounded queries are policed by `tests/test_query_contract.py`.
    """
    documents = await query.to_list(limit + 1)
    if len(documents) > limit:
        logger.error(
            "query '%s' returned more than %d documents — result truncated, pagination needed",
            what,
            limit,
        )
        return documents[:limit]
    return documents


class TenantScopedRepository[DocT: TenantOwnedMixin]:
    document: type[DocT]

    def __init__(self, organization_id: PydanticObjectId) -> None:
        self.organization_id = organization_id

    def scoped(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        """The only way into tenant-owned data. Do not bypass."""
        return {**(query or {}), "organization_id": self.organization_id}
