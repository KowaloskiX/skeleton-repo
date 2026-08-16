"""Health logic — pure, no HTTP."""

import asyncio
import logging
from collections.abc import Awaitable

from limits.aio.storage import Storage

from app.core.config import get_settings
from app.core.domain.health import (
    DependencyCheck,
    DependencyState,
    HealthReport,
    ReadinessReport,
)
from app.db.client import Database

logger = logging.getLogger(__name__)

# The probe must answer faster than the orchestrator would consider it hung. The Mongo client
# has its own `serverSelectionTimeoutMS`, the rate-limit storage does not — hence a shared
# budget here.
_PROBE_TIMEOUT_SECONDS = 2.0


def check_health() -> HealthReport:
    return HealthReport(status="ok", env=get_settings().app_env)


async def _check(name: str, probe: Awaitable[object]) -> DependencyCheck:
    """Runs a probe under a timeout and turns EVERY failure into a `DOWN` state.

    A readiness probe must not raise: an exception would turn a readable 503 listing the
    dependencies into a 500 with a traceback, and an orchestrator treats both the same way
    while diagnosis gets harder.
    """
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            await probe
    except Exception as error:  # deliberately broad — see the docstring
        logger.warning("dependency '%s' unavailable: %s", name, error)
        # The error text does NOT reach the response: it contains host names and usernames
        # from the connection URL. Details stay in the log.
        return DependencyCheck(name=name, state=DependencyState.DOWN)
    return DependencyCheck(name=name, state=DependencyState.UP)


async def check_readiness(
    database: Database, rate_limit_storage: Storage | None, *, indexes_present: bool = True
) -> ReadinessReport:
    """Checks the dependencies without which a request would fail anyway.

    `rate_limit_storage=None` means "the counter lives in process memory" — that is not an
    external dependency, there is nothing to ping and it cannot fail separately from the
    application. The HTTP layer makes that call based on configuration; the service does not
    guess from the type.

    Probes run **concurrently**: with two unavailable dependencies, waiting sequentially would
    add up the timeouts and the probe itself would blow the orchestrator's budget.
    """
    # Not a probe but a startup fact: the declared indexes either exist or the deployment step
    # was skipped, and then every query that needs one is a collection scan. Reporting it here
    # keeps such an instance out of the load balancer.
    index_check = DependencyCheck(
        name="indexes",
        state=DependencyState.UP if indexes_present else DependencyState.DOWN,
    )

    if rate_limit_storage is None:
        mongo_check = await _check("mongodb", database.ping())
        return ReadinessReport(
            checks=(
                mongo_check,
                DependencyCheck(name="rate_limit_storage", state=DependencyState.NOT_CONFIGURED),
                index_check,
            )
        )

    checks = await asyncio.gather(
        _check("mongodb", database.ping()),
        _check("rate_limit_storage", rate_limit_storage.check()),
    )
    return ReadinessReport(checks=(*checks, index_check))
