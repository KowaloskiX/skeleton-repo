"""FastAPI dependencies from the core layer. Factories, never module-level singletons.

The database connection lives in `app.db.deps` — `core` must not import `db`.
"""

from typing import Annotated

from fastapi import Depends, Request
from limits.aio.storage import Storage

from app.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_rate_limit_storage(request: Request) -> Storage:
    """The same object the rate-limit middleware uses — the readiness probe has to check the
    actual connection, not a freshly built one next to it."""
    storage: Storage | None = getattr(request.app.state, "rate_limit_storage", None)
    if storage is None:  # pragma: no cover - configuration error, not a runtime path
        raise RuntimeError("Rate limit storage was not stored on the application state")
    return storage


RateLimitStorageDep = Annotated[Storage, Depends(get_rate_limit_storage)]
