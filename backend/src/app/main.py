"""FastAPI entry point. All routes live under /api (same origin as the frontend)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.errors_http import register_error_handlers
from app.core.http_security import (
    BodySizeLimitMiddleware,
    CsrfMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import RequestIdMiddleware, configure_logging
from app.core.rate_limit import (
    RateLimitMiddleware,
    build_rate_limit_rules,
    build_rate_limit_storage,
)
from app.db.client import Database
from app.db.indexes import verify_indexes
from app.documents import DOCUMENT_MODELS
from app.routes.api import api_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """`settings` is injected explicitly so tests can build an application with different
    limits without touching environment variables."""
    resolved = settings or get_settings()
    # JSON only outside dev/test: locally readability in a terminal wins, on a deployment
    # machine parsability by the log collector does.
    configure_logging(json_format=not resolved.expose_api_docs)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Mongo client and document registration once per process — not per request."""
        database = Database.from_settings(resolved)
        # On dev/test it is convenient to create indexes at startup; on staging/prod that is
        # a separate deployment step (`uv run ensure-indexes`) so boot does not build indexes.
        await database.init_documents(
            DOCUMENT_MODELS, create_indexes=resolved.create_indexes_on_startup
        )
        # Checked once, not per request: a missing index is a deployment mistake, not a
        # fluctuating condition. Readiness reports it, so an instance whose database lacks the
        # indexes stays out of the load balancer instead of turning every query into a scan.
        app.state.indexes_present = await verify_indexes(database.database, DOCUMENT_MODELS)
        app.state.database = database
        try:
            yield
        finally:
            await database.dispose()

    app = FastAPI(
        title="Skeleton API",
        version="0.0.0",
        lifespan=lifespan,
        # Outside dev/test Swagger and the schema are disabled: in production they are a
        # ready-made manual for the API, complete with the error-code catalogue and the
        # ability to send POSTs.
        docs_url="/docs" if resolved.expose_api_docs else None,
        redoc_url="/redoc" if resolved.expose_api_docs else None,
        openapi_url="/openapi.json" if resolved.expose_api_docs else None,
    )

    # Rate-limit storage also goes on `app.state`: the readiness probe must ping THIS object,
    # not a freshly built connection next to it.
    rate_limit_storage = build_rate_limit_storage(resolved)
    app.state.rate_limit_storage = rate_limit_storage

    # Order matters. `add_middleware` wraps from the outside, so whatever is added LAST is the
    # outermost layer. Intended request handling order:
    #   request id -> security headers -> CORS -> body size limit -> rate limit
    #     -> CSRF -> application
    # CSRF sits innermost on purpose: requests it rejects have already been counted by the
    # rate limiter, so flooding with bad tokens does not bypass the counter.
    app.add_middleware(CsrfMiddleware, settings=resolved)
    app.add_middleware(
        RateLimitMiddleware,
        rules=build_rate_limit_rules(resolved),
        storage=rate_limit_storage,
        trusted_proxy_hops=resolved.trusted_proxy_hops,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=resolved.max_request_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins_list,
        allow_credentials=True,
        # Narrowed to the actual surface: the browser does not need more, and `*` alongside
        # cookies is needlessly wide.
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=resolved)
    # OUTERMOST: the identifier must exist before anything logs — including logs from the
    # other middleware.
    app.add_middleware(RequestIdMiddleware)

    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
