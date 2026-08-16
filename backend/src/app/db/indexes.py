"""Verifying that the indexes the models declare actually exist in the database.

On dev the application creates them at startup, so this is trivially true. On staging and
production they come from a deployment step (`uv run ensure-indexes`), and forgetting that step
does not fail anything: the application starts, serves traffic, and every query that should have
used the missing index quietly turns into a collection scan. The database gets slower and slower
and nothing says why.

So we check once at startup and report the answer through readiness. A missing index means the
instance stays out of the load balancer instead of degrading the whole cluster.
"""

import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)


def _declared_index_names(document: type[Any]) -> set[str]:
    """Index names from the document's `Settings.indexes`.

    Read from the class declaration rather than from `get_settings()`: after initialization
    Beanie replaces the entries with its own wrapper type, while the declaration stays plain
    `pymongo.IndexModel`, which is the shape we want to compare against.

    Every index in this repository is declared with an explicit `name=`, and that is what makes
    the comparison possible — without names Mongo derives them from the keys and the two sides
    stop lining up.
    """
    declared = getattr(getattr(document, "Settings", None), "indexes", None) or []
    names: set[str] = set()
    for index in declared:
        name = index.document.get("name")
        if name:
            names.add(str(name))
    return names


async def missing_indexes(
    database: AsyncDatabase[dict[str, Any]], documents: tuple[type[Any], ...]
) -> dict[str, set[str]]:
    """Returns `collection -> index names that are declared but absent`. Empty means healthy."""
    missing: dict[str, set[str]] = {}
    for document in documents:
        collection = document.get_settings().name
        declared = _declared_index_names(document)
        if not declared:
            continue
        existing = set(await database[collection].index_information())
        absent = declared - existing
        if absent:
            missing[collection] = absent
    return missing


async def verify_indexes(
    database: AsyncDatabase[dict[str, Any]], documents: tuple[type[Any], ...]
) -> bool:
    """Checks every declared index and logs loudly what is missing. `True` means all present."""
    missing = await missing_indexes(database, documents)
    if not missing:
        return True

    for collection, names in sorted(missing.items()):
        logger.error(
            "collection '%s' is missing declared indexes: %s — run `uv run ensure-indexes` "
            "before letting traffic in; queries on those fields are collection scans",
            collection,
            ", ".join(sorted(names)),
        )
    return False
