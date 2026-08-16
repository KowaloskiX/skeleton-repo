"""Liveness vs readiness — the distinction that decides behaviour during a database outage.

Confusing them is a classic: a liveness probe that checks the database turns a brief Mongo
outage into a restart loop across every pod. A readiness probe does the right thing instead —
it takes the instance out of the load balancer and waits.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from limits.aio.storage import MemoryStorage

from app.core.config import Settings, get_settings
from app.core.domain.health import DependencyState
from app.db.client import Database
from app.main import create_app


class _BrokenStorage(MemoryStorage):
    """Impersonates an unreachable Redis."""

    async def check(self) -> bool:
        raise ConnectionError("redis is not responding")


class _BrokenDatabase:
    """A database that does not answer a ping."""

    async def ping(self) -> None:
        raise ConnectionError("mongo is not responding")


def _client_for(application: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


@pytest.fixture
async def degraded_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An application with both dependencies down.

    `rate_limit_storage_url` has to be non-empty, otherwise the storage is not checked at all
    (see `check_readiness`) — i.e. the test would not test what it thinks it does.
    """
    settings = settings.model_copy(update={"rate_limit_storage_url": "redis://does-not-exist:6379"})
    application = create_app(settings)
    application.state.database = _BrokenDatabase()
    application.state.rate_limit_storage = _BrokenStorage()
    application.dependency_overrides[get_settings] = lambda: settings
    async with _client_for(application) as http_client:
        yield http_client


async def test_liveness_does_not_touch_dependencies(degraded_client: AsyncClient) -> None:
    """The heart of the distinction: with the database down, liveness MUST still return 200.

    Otherwise Kubernetes declares the process dead and restarts it — a restart will not fix
    somebody else's database, but it will drop caches and open connections.
    """
    response = await degraded_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_every_dependency(client: AsyncClient) -> None:
    response = await client.get("/api/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    states = {check["name"]: check["state"] for check in body["checks"]}
    assert states["mongodb"] == DependencyState.UP
    # In tests the limit is counted in process memory — that is not an external dependency.
    assert states["rate_limit_storage"] == DependencyState.NOT_CONFIGURED


async def test_readiness_returns_503_when_a_dependency_is_down(
    degraded_client: AsyncClient,
) -> None:
    """503 takes the instance out of the load balancer without killing it."""
    response = await degraded_client.get("/api/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert {
        check["name"] for check in body["checks"] if check["state"] == DependencyState.DOWN
    } == {
        "mongodb",
        "rate_limit_storage",
    }


async def test_readiness_does_not_leak_connection_details(
    degraded_client: AsyncClient,
) -> None:
    """A connection error message contains the host, the port and the username from the URL.

    The probe is usually exposed more widely than the rest of the API (orchestrator,
    monitoring), so the details stay in the log.
    """
    body = (await degraded_client.get("/api/health/ready")).text

    assert "not responding" not in body, "the exception message leaked into the response"
    assert "mongodb://" not in body


async def test_readiness_is_exempt_from_rate_limiting(
    settings: Settings, database: Database
) -> None:
    """A throttled probe looks like an application outage to the orchestrator — and a rolling
    update then starts killing healthy pods."""
    tight = settings.model_copy(update={"global_rate_limit": "2/minute"})
    application = create_app(tight)
    application.state.database = database
    application.dependency_overrides[get_settings] = lambda: tight

    async with _client_for(application) as http_client:
        statuses = [(await http_client.get("/api/health/ready")).status_code for _ in range(5)]

    assert statuses == [200] * 5, statuses


def test_probe_paths_stay_in_sync_with_the_exempt_list() -> None:
    """Contract: every probe must be exempt from the rate limit. A new `/health/*` route that
    is not added to the list stops answering under load — and nobody notices until the first
    incident."""
    from app.core.rate_limit import RATE_LIMIT_EXEMPT_PATHS

    application: Any = create_app()
    probe_paths = {
        route.path
        for route in application.routes
        if getattr(route, "path", "").startswith("/api/health")
    }
    assert probe_paths <= RATE_LIMIT_EXEMPT_PATHS, (
        f"probes outside the exempt list: {probe_paths - RATE_LIMIT_EXEMPT_PATHS}"
    )


async def test_missing_indexes_keep_the_instance_out_of_the_load_balancer(
    settings: Settings, database: Database
) -> None:
    """On staging and production the indexes come from a deployment step, and skipping it fails
    nothing by itself: the application starts and every query that needed an index quietly
    becomes a collection scan. Readiness is where that has to surface."""
    application = create_app(settings)
    application.state.database = database
    application.state.indexes_present = False
    application.dependency_overrides[get_settings] = lambda: settings

    async with _client_for(application) as http_client:
        response = await http_client.get("/api/health/ready")

    assert response.status_code == 503
    states = {check["name"]: check["state"] for check in response.json()["checks"]}
    assert states["indexes"] == DependencyState.DOWN
    assert states["mongodb"] == DependencyState.UP, "the database itself is fine — only the setup"


async def test_declared_indexes_are_actually_created(database: Database) -> None:
    """The declaration and the database have to agree. A named index that never reaches Mongo is
    invisible: queries keep working, just by scanning."""
    from app.db.indexes import missing_indexes
    from app.documents import DOCUMENT_MODELS

    assert await missing_indexes(database.database, DOCUMENT_MODELS) == {}
