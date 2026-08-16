"""Domain error codes. Never a bare string — see docs/conventions/01."""

from enum import StrEnum


class AuthError(StrEnum):
    INVALID_CREDENTIALS = "invalid_credentials"
    EMAIL_TAKEN = "email_taken"
    SESSION_INVALID = "session_invalid"
    ACCOUNT_DISABLED = "account_disabled"


class ApiError(StrEnum):
    """Edge-layer errors — they do not belong to any business domain."""

    RATE_LIMITED = "rate_limited"
    CSRF_INVALID = "csrf_invalid"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    VALIDATION_FAILED = "validation_failed"
    INTERNAL_ERROR = "internal_error"
