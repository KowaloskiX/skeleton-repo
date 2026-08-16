"""Mongo query contract — two things the database will not enforce on its own.

1. **Every query must hit an index.** The test server runs with `notablescan`, so a collection
   scan ends in an error. This file makes sure the guard is ON — otherwise somebody removes
   the line from `conftest.py` and the whole suite stops catching missing indexes without a
   single test result changing.
2. **Every query must have a ceiling on the number of results.** `to_list()` with no argument
   pulls the entire result set into memory. With four collections that is nothing; with the
   first audit-event collection it is an OOM.
"""

import ast
from pathlib import Path

import pytest
from pymongo.errors import OperationFailure

from app.db.client import Database
from app.repositories.base import MAX_DOCUMENTS_PER_QUERY

REPOSITORIES_DIR = Path(__file__).resolve().parent.parent / "src" / "app" / "repositories"


def _unbounded_to_list_calls(source: Path) -> list[int]:
    """Line numbers of `.to_list()` calls with no argument."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_list"
        and not node.args
        and not node.keywords
    ]


def test_repositories_have_no_unbounded_queries() -> None:
    offenders = {
        path.name: lines
        for path in sorted(REPOSITORIES_DIR.glob("*.py"))
        if (lines := _unbounded_to_list_calls(path))
    }
    assert not offenders, (
        f"`to_list()` without a ceiling: {offenders}. Use `bounded_to_list(...)` from "
        "`app.repositories.base` — otherwise one query can pull an entire collection into "
        "memory."
    )


def test_query_limit_is_sane() -> None:
    """The ceiling has to be a real constraint, not decoration."""
    assert 10 <= MAX_DOCUMENTS_PER_QUERY <= 1000


async def test_collection_scans_are_rejected_in_tests(database: Database) -> None:
    """Proof that `notablescan` really is active on the test server.

    `password_hash` deliberately has no index — it is a field nobody filters on. If this test
    stops raising, we have lost the missing-index detector for the ENTIRE suite.
    """
    with pytest.raises(OperationFailure) as failure:
        await database.database["users"].find_one({"password_hash": "anything"})

    assert "notablescan" in str(failure.value), (
        "an unindexed query passed, or failed for another reason — check whether the "
        "`mongodb_url` fixture in conftest.py still sets `notablescan`"
    )
