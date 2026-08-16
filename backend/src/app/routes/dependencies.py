"""HTTP dependencies for auth: the service and the current user."""

from typing import Annotated

from fastapi import Depends, Request
from starlette import status

from app.core.config import Settings
from app.core.deps import SettingsDep
from app.core.domain.errors import AuthError
from app.core.domain.identity import AuthenticatedUser
from app.core.domain.result import Ok
from app.core.errors_http import DomainHTTPError
from app.db.deps import DbDep
from app.services.auth import AuthService

CSRF_HEADER_NAME = "X-CSRF-Token"


def get_auth_service(database: DbDep, settings: SettingsDep) -> AuthService:
    return AuthService(database, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    request: Request,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> AuthenticatedUser:
    user = await _resolve_optional_user(request, service, settings)
    if user is None:
        raise DomainHTTPError(
            AuthError.SESSION_INVALID,
            status.HTTP_401_UNAUTHORIZED,
            "No active session.",
        )
    return user


async def get_optional_user(
    request: Request,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> AuthenticatedUser | None:
    return await _resolve_optional_user(request, service, settings)


async def _resolve_optional_user(
    request: Request, service: AuthService, settings: Settings
) -> AuthenticatedUser | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    result = await service.resolve_session(token)
    return result.value if isinstance(result, Ok) else None


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_user)]
