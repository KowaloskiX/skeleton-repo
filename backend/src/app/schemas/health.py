"""Response schemas for `/api/health` and `/api/health/ready`."""

from typing import Literal

from pydantic import BaseModel

from app.core.domain.environments import AppEnv
from app.core.domain.health import DependencyState


class HealthStatus(BaseModel):
    status: Literal["ok"]
    env: AppEnv


class DependencyStatus(BaseModel):
    name: str
    state: DependencyState


class ReadinessResponse(BaseModel):
    """`ready=false` ships with status 503 — orchestrators read the status, humans read the
    list."""

    ready: bool
    checks: list[DependencyStatus]
