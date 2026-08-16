"""HTTP for auth: statuses, cookies, mapping onto schemas. Zero business logic."""

from fastapi import APIRouter, Request, Response
from starlette import status

from app.core.deps import SettingsDep
from app.core.domain.identity import AuthenticatedUser
from app.core.domain.result import Ok
from app.core.errors_http import ErrorResponse
from app.routes.cookies import apply_session, clear_session_cookie, ensure_csrf_cookie
from app.routes.dependencies import AuthServiceDep, CurrentUser, OptionalUser
from app.routes.errors import auth_failure
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    MessageResponse,
    OrganizationSummary,
    RegisterRequest,
    SessionResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_response(user: AuthenticatedUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        organizations=[
            OrganizationSummary(id=org.id, name=org.name, slug=org.slug, role=org.role)
            for org in user.organizations
        ],
    )


@router.get("/session", operation_id="auth-session")
async def read_session(
    request: Request,
    response: Response,
    settings: SettingsDep,
    user: OptionalUser,
) -> SessionResponse:
    """Session state plus CSRF cookie issuance. The frontend calls this on application start."""
    ensure_csrf_cookie(request, response, settings)
    return SessionResponse(user=_to_response(user) if user else None)


@router.post(
    "/register",
    operation_id="auth-register",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def register(
    response: Response,
    payload: RegisterRequest,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> CurrentUserResponse:
    result = await service.register(
        email=payload.email,
        password=payload.password,
        organization_name=payload.organization_name,
    )
    if not isinstance(result, Ok):
        raise auth_failure(result.error)
    apply_session(response, settings, result.value)
    return _to_response(result.value.user)


@router.post(
    "/login",
    operation_id="auth-login",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def login(
    response: Response,
    payload: LoginRequest,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> CurrentUserResponse:
    result = await service.login(email=payload.email, password=payload.password)
    if not isinstance(result, Ok):
        raise auth_failure(result.error)
    apply_session(response, settings, result.value)
    return _to_response(result.value.user)


@router.post(
    "/logout",
    operation_id="auth-logout",
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    _user: CurrentUser,
) -> MessageResponse:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await service.logout(token)
    clear_session_cookie(response, settings)
    return MessageResponse(message="Signed out.")
