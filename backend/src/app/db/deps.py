"""FastAPI dependency providing the database connection.

Lives in `app.db` rather than `app.core`, because `core` is the lowest layer and must not
reach upwards — enforced by the `layers` contract in `.importlinter`.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.db.client import Database


def get_database(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:  # pragma: no cover - configuration error, not a runtime path
        raise RuntimeError("Database was not initialized in the application lifespan")
    return database


DbDep = Annotated[Database, Depends(get_database)]
