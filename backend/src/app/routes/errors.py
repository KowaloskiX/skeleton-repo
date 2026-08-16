"""Mapping of domain errors onto HTTP.

A separate module because this is the only place that knows both worlds: `AuthError` codes
from the domain and HTTP statuses. Routers therefore carry no lookup tables, and adding a
new error is one line in one file.
"""

from starlette import status

from app.core.domain.errors import AuthError
from app.core.errors_http import DomainHTTPError

_STATUS: dict[AuthError, int] = {
    AuthError.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    AuthError.SESSION_INVALID: status.HTTP_401_UNAUTHORIZED,
    AuthError.ACCOUNT_DISABLED: status.HTTP_403_FORBIDDEN,
    AuthError.EMAIL_TAKEN: status.HTTP_409_CONFLICT,
}

_MESSAGE: dict[AuthError, str] = {
    AuthError.INVALID_CREDENTIALS: "Invalid email or password.",
    AuthError.SESSION_INVALID: "No active session.",
    AuthError.ACCOUNT_DISABLED: "This account is disabled.",
    AuthError.EMAIL_TAKEN: "An account with this email already exists.",
}


def auth_failure(error: AuthError) -> DomainHTTPError:
    return DomainHTTPError(error, _STATUS[error], _MESSAGE[error])
