"""One place showing the entire HTTP surface of the application.

A new route means a new module in `app/routes/` plus one `include_router` line here. That way
the answer to "which endpoints do we expose" is a single file rather than a tree walk.
"""

from fastapi import APIRouter

from app.routes.auth import router as auth_router
from app.routes.health import router as health_router

# Everything under /api — same origin as the frontend, so the session cookie is first-party.
api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
