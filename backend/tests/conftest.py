"""Test fixtures: a real Mongo in a container, the same image as local dev.

The Atlas-local image rather than plain `mongo`, because the tests have to exercise
transactions (those require a replica set) and will need `$vectorSearch` once the AI layer
arrives.
"""

from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testcontainers.community.mongodb import MongoDBAtlasLocalContainer

from app.core.config import Settings, get_settings
from app.core.http_security import CSRF_HEADER_NAME
from app.db.client import Database
from app.documents import DOCUMENT_MODELS
from app.main import create_app

_MONGO_IMAGE = "mongodb/mongodb-atlas-local:8.2"
_TEST_DATABASE = "app_test"


@pytest.fixture(scope="session")
def mongodb_url() -> Iterator[str]:
    with MongoDBAtlasLocalContainer(_MONGO_IMAGE) as container:
        # `notablescan` makes the server REJECT any query that would have to scan a
        # collection. That turns the WHOLE suite into a missing-index detector: a new
        # repository filtering on an unindexed field fails a test rather than production.
        # It is a server setting, not a client one — so it covers everything the tests run.
        container.get_connection_client().admin.command({"setParameter": 1, "notablescan": 1})
        # `get_connection_url()` appends `?directConnection=true` — without it the client
        # would try to resolve the container name advertised by the replica set.
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def settings(mongodb_url: str) -> Settings:
    return Settings(
        app_env="test",
        mongodb_url=mongodb_url,
        mongodb_database=_TEST_DATABASE,
        auth_secret="test-secret-not-used-in-production",
    )


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database.from_settings(settings)
    await db.init_documents(DOCUMENT_MODELS, create_indexes=True)
    yield db
    # We clear documents, not collections — indexes (including unique ones) stay, so every
    # test runs under the same constraints as production.
    for model in DOCUMENT_MODELS:
        await db.database[model.get_settings().name].delete_many({})
    await db.dispose()


@pytest.fixture
def app(settings: Settings, database: Database) -> Iterator[FastAPI]:
    application = create_app(settings)
    application.state.database = database
    application.dependency_overrides[get_settings] = lambda: settings
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def csrf(client: AsyncClient, settings: Settings) -> Callable[[], dict[str, str]]:
    """`GET /api/auth/session` issues the CSRF cookie, which has to be echoed in a header.

    Returns a factory rather than a ready dict — the token rotates after login, so every
    request must take the current value from the cookie (exactly what the frontend does).
    """
    await client.get("/api/auth/session")

    def headers() -> dict[str, str]:
        token = client.cookies.get(settings.effective_csrf_cookie_name)
        assert token is not None, "the CSRF cookie is missing"
        return {CSRF_HEADER_NAME: token}

    return headers
