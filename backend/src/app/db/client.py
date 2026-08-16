"""Mongo connection and the transaction boundary.

No module-level singletons — the `Database` instance lives in the application `lifespan` and
is injected via `Depends`.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings


@dataclass(slots=True)
class Database:
    client: AsyncMongoClient[dict[str, Any]]
    database: AsyncDatabase[dict[str, Any]]

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
            settings.mongodb_url,
            # Datetimes come back timezone-aware; without this they are naive UTC and comparing
            # them against an aware `utc_now()` raises.
            tz_aware=True,
            # By default PyMongo waits 30 s for server selection. With a dead database that
            # means requests hanging for half a minute, an exhausted pool and proxy timeouts
            # instead of a fast failure. Set explicitly and short.
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
            # Budget for the WHOLE operation (CSOT), not just the socket — also catches
            # slow queries.
            timeoutMS=settings.mongodb_operation_timeout_ms,
            # Explicit, because the default of 100 per process is a number nobody chose:
            # `workers * replicas * pool` has to stay under the cluster's connection limit.
            maxPoolSize=settings.mongodb_max_pool_size,
        )
        return cls(client=client, database=client[settings.mongodb_database])

    async def ping(self) -> None:
        """Readiness probe. `ping` on `admin` is cheap and needs no data permissions.

        We deliberately do not query application collections: the probe checks server
        availability, not database contents — otherwise an empty database would look like
        an outage.
        """
        await self.client.admin.command("ping")

    async def init_documents(
        self, document_models: Sequence[type[Any]], *, create_indexes: bool
    ) -> None:
        """Registers models with Beanie. Optionally creates missing indexes.

        `create_indexes=False` on staging/prod is deliberate: building an index on a large
        collection eats I/O, and application start is not the moment for that. There indexes
        are created by a separate release step (`uv run ensure-indexes`) — the same way
        `migrate` is a deployment step rather than a boot side effect.
        """
        await init_beanie(
            database=self.database,
            document_models=list(document_models),
            skip_indexes=not create_indexes,
        )

    async def in_transaction[T](self, operation: Callable[[AsyncClientSession], Awaitable[T]]) -> T:
        """An atomic unit of work. Requires a replica set — see docker-compose.yml.

        Deliberately `with_transaction` rather than a manual `start_transaction`: Mongo
        **requires** retrying transactions labelled `TransientTransactionError` (e.g.
        `WriteConflict` when two concurrent registrations race on the same email — measured).
        The manual version did not, and returned 500 instead of the correct result.
        `with_transaction` implements the required retry loops for `TransientTransactionError`
        and `UnknownTransactionCommitResult`.

        **The callback must be replayable** — it may run more than once. Do not put
        irreversible or expensive work in it (password hashing, sending email); prepare those
        before entering the transaction.

        Writes inside MUST receive `session=`, otherwise they escape the transaction.
        Operations run sequentially: a client session is not safe for concurrent queries.
        """
        async with self.client.start_session() as session:
            return await session.with_transaction(operation)

    async def dispose(self) -> None:
        await self.client.close()
