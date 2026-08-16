"""Health check results — pure domain, without Pydantic and without HTTP.

The service returns these and the router maps them onto a response schema. With a single field
that looks like ceremony, but it is the pattern: **a service never returns an API contract**,
otherwise changes to the HTTP response start leaking down through the layers.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.core.domain.environments import AppEnv


class DependencyState(StrEnum):
    """State of a single external dependency."""

    UP = "up"
    DOWN = "down"
    # Configured absence — e.g. the rate limit counted in process memory rather than in Redis.
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: Literal["ok"]
    env: AppEnv


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    state: DependencyState
    detail: str | None = None

    @property
    def blocks_traffic(self) -> bool:
        """Only `DOWN` cuts traffic off. `NOT_CONFIGURED` is a deliberate configuration choice
        rather than an outage — otherwise a dev machine without Redis would never be ready."""
        return self.state is DependencyState.DOWN


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Readiness is not liveness. Liveness answers "the process is alive" and must not depend
    on anything external — otherwise a brief database outage causes a restart loop. Readiness
    answers "I can serve a request", which is exactly why it checks dependencies."""

    checks: tuple[DependencyCheck, ...]

    @property
    def ready(self) -> bool:
        return not any(check.blocks_traffic for check in self.checks)
