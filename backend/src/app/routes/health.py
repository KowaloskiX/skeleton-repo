"""Health endpoints — thin wrappers over the logic."""

from fastapi import APIRouter, Request, Response
from starlette import status

from app.core.deps import RateLimitStorageDep, SettingsDep
from app.core.domain.health import ReadinessReport
from app.db.deps import DbDep
from app.schemas.health import DependencyStatus, HealthStatus, ReadinessResponse
from app.services.health import check_health, check_readiness

router = APIRouter(tags=["health"])


@router.get("/health", operation_id="health-get")
async def health() -> HealthStatus:
    """**Liveness.** Answers "the process is alive" and deliberately touches neither the
    database nor Redis.

    If it did, a brief database outage would end in pods restarting in a loop — a dependency
    outage turned into an application outage.

    Exempt from rate limiting (`RATE_LIMIT_EXEMPT_PATHS`): orchestrators hit this often, and a
    throttled probe looks like an outage to them.
    """
    report = check_health()
    return HealthStatus(status=report.status, env=report.env)


@router.get(
    "/health/ready",
    operation_id="health-ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(
    request: Request,
    response: Response,
    database: DbDep,
    rate_limit_storage: RateLimitStorageDep,
    settings: SettingsDep,
) -> ReadinessResponse:
    """**Readiness.** Answers "I can serve a request", so it checks dependencies.

    503 takes the instance out of the load balancer without killing it — exactly what we want
    when the database dies: pods wait instead of restarting over and over.
    """
    # Without a configured URL the counter lives in process memory and there is nothing to ping.
    shared_storage = rate_limit_storage if settings.rate_limit_storage_url else None
    # Established once during startup — see the lifespan in `app.main`.
    indexes_present = bool(getattr(request.app.state, "indexes_present", True))
    report = await check_readiness(database, shared_storage, indexes_present=indexes_present)
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return _to_response(report)


def _to_response(report: ReadinessReport) -> ReadinessResponse:
    return ReadinessResponse(
        ready=report.ready,
        checks=[DependencyStatus(name=check.name, state=check.state) for check in report.checks],
    )
