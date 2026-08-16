"""Rate limiting on Redis — the reason Redis is in the stack at all.

An in-memory limit works per instance: two replicas mean twice the budget for an attacker.
This file proves that with shared storage the counter is one for the whole fleet, and that a
dead Redis does not take the application down.
"""

from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from limits.aio.storage import RedisStorage
from testcontainers.community.redis import RedisContainer

from app.core.config import Settings, get_settings
from app.core.rate_limit import build_rate_limit_storage
from app.db.client import Database
from app.main import create_app

_REDIS_IMAGE = "redis:8-alpine"
SHARED_LIMIT = 4


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer(_REDIS_IMAGE) as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}"


@pytest.fixture
def redis_settings(settings: Settings, redis_url: str) -> Settings:
    return settings.model_copy(
        update={
            "rate_limit_storage_url": redis_url,
            "global_rate_limit": f"{SHARED_LIMIT}/minute",
        }
    )


@pytest.fixture(autouse=True)
async def _clean_counters(redis_settings: Settings) -> AsyncIterator[None]:
    """The container is session-scoped, so counters must be reset between tests."""
    storage = build_rate_limit_storage(redis_settings)
    await storage.reset()
    yield
    await storage.reset()


@pytest.fixture
def make_client(redis_settings: Settings, database: Database) -> Callable[[], AsyncClient]:
    """A factory of **independent application instances**.

    Each gets its own storage object (built by `create_app`), so if the counter turns out to be
    shared, it is thanks to Redis — not to a shared Python object.
    """

    def factory() -> AsyncClient:
        app: FastAPI = create_app(redis_settings)
        app.state.database = database
        app.dependency_overrides[get_settings] = lambda: redis_settings
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return factory


async def test_limit_is_shared_between_app_instances(
    make_client: Callable[[], AsyncClient],
) -> None:
    first, second = make_client(), make_client()
    async with first, second:
        # Budget spread across two instances — together exactly the limit.
        for _ in range(SHARED_LIMIT // 2):
            assert (await first.get("/api/auth/session")).status_code == 200
            assert (await second.get("/api/auth/session")).status_code == 200

        # The next request must get a 429 on BOTH instances — there is one counter.
        assert (await first.get("/api/auth/session")).status_code == 429
        assert (await second.get("/api/auth/session")).status_code == 429


async def test_memory_storage_would_not_share(settings: Settings, database: Database) -> None:
    """Negative control: without shared storage each instance has its own budget.

    This test describes the behaviour Redis fixes — if it passed the same way as the one above,
    it would mean the sharing comes from somewhere else and that test proves nothing.
    """
    per_instance = settings.model_copy(
        update={"rate_limit_storage_url": "", "global_rate_limit": f"{SHARED_LIMIT}/minute"}
    )

    def make() -> AsyncClient:
        app = create_app(per_instance)
        app.state.database = database
        app.dependency_overrides[get_settings] = lambda: per_instance
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    first, second = make(), make()
    async with first, second:
        for _ in range(SHARED_LIMIT):
            assert (await first.get("/api/auth/session")).status_code == 200
        assert (await first.get("/api/auth/session")).status_code == 429
        # The second instance has an untouched budget — exactly the problem Redis solves.
        assert (await second.get("/api/auth/session")).status_code == 200


async def test_dead_redis_degrades_to_process_memory_instead_of_disabling_the_limit(
    make_client: Callable[[], AsyncClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead Redis must not block traffic — but it must not unblock it either.

    Fail-open (let everything through) would mean one `redis-cli SHUTDOWN` removes the login
    limit from the entire fleet. So we drop to a counter in process memory: the budget becomes
    N-fold with N replicas, but the wall is still there.
    """

    async def explode(*_: object, **__: object) -> bool:
        raise RuntimeError("redis is down")

    monkeypatch.setattr(RedisStorage, "acquire_entry", explode)

    async with make_client() as client:
        statuses = [
            (await client.get("/api/auth/session")).status_code for _ in range(SHARED_LIMIT + 1)
        ]

    assert statuses[:SHARED_LIMIT] == [200] * SHARED_LIMIT, "a Redis outage must not stop traffic"
    assert statuses[-1] == 429, "after a Redis outage the limit must still apply, just locally"


def test_plain_redis_url_is_upgraded_to_async(settings: Settings) -> None:
    """You paste `redis://…` from the provider's console, we add `async+` — without it `limits`
    would return a storage backend that blocks the event loop."""
    storage = build_rate_limit_storage(
        settings.model_copy(update={"rate_limit_storage_url": "redis://localhost:6379"})
    )
    assert type(storage).__module__.startswith("limits.aio.storage")
