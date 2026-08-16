"""One error shape for the whole API, in one place.

Every failure — a domain error, a 404, a bad method, a crash — comes back as the same object:
`{code, message, request_id}`. Two reasons. The generated TS client then has one type to handle
instead of three shapes depending on which layer rejected the request. And `request_id` lets a
user paste an identifier from the screen that maps straight to a line in the logs.

The code travels in the body as `code`, so the client gets a typed union rather than a bare
string inside `detail`.
"""

import logging
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.domain.errors import ApiError
from app.core.observability import request_id

logger = logging.getLogger(__name__)

# Status -> (code, message) for failures produced by the framework rather than by our code.
# The message is deliberately generic: it is what an anonymous caller sees.
_FRAMEWORK_ERRORS: dict[int, tuple[ApiError, str]] = {
    status.HTTP_404_NOT_FOUND: (ApiError.NOT_FOUND, "No such resource."),
    status.HTTP_405_METHOD_NOT_ALLOWED: (
        ApiError.METHOD_NOT_ALLOWED,
        "This method is not allowed on this resource.",
    ),
}


class ErrorResponse(BaseModel):
    code: str
    message: str
    # Present on every error response; matches the `X-Request-Id` header. Optional in the schema
    # because a client must not depend on it — it is a diagnostic aid, not part of the logic.
    request_id: str | None = None


class DomainHTTPError(Exception):
    def __init__(self, code: StrEnum, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


def error_response(status_code: int, code: StrEnum, message: str, **extra: Any) -> JSONResponse:
    """Builds an error response with the current request identifier attached.

    Used by the handlers here and by the edge middleware, so a 403 from CSRF looks exactly like
    a 404 from the router.
    """
    body = ErrorResponse(code=code.value, message=message, request_id=request_id.get()).model_dump()
    return JSONResponse(status_code=status_code, content={**body, **extra})


def _without_submitted_values(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Strips the `input` key from validation errors.

    Pydantic v2 puts the RAW submitted value there, so FastAPI's default 422 response was
    echoing the user's own password back — straight into proxy logs, Sentry and HAR files sent
    to support.
    """
    return [
        {key: value for key, value in error.items() if key != "input"}
        for error in errors
        if isinstance(error, dict)
    ]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainHTTPError)
    async def _handle_domain_error(_: Request, exc: DomainHTTPError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # `detail` keeps the field-level information FastAPI documents in the schema; the
        # envelope is added on top so the client has one shape to handle.
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ApiError.VALIDATION_FAILED,
            "The request body failed validation.",
            detail=_without_submitted_values(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Covers what the framework raises on its own: 404, 405 and any bare HTTPException.

        Without this, an unknown path answered `{"detail": "Not Found"}` — a different shape
        from every other error in the API, so the client fell back to a generic message.
        """
        code, message = _FRAMEWORK_ERRORS.get(
            exc.status_code, (ApiError.INTERNAL_ERROR, str(exc.detail))
        )
        response = error_response(exc.status_code, code, message)
        # 405 must carry Allow — without it the response is not a valid HTTP 405.
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        """The last line: an unhandled exception must not reach the client as text.

        Starlette's default returns a plain-text "Internal Server Error" — a different content
        type from the rest of the API. The exception message stays in the log because it tends
        to contain connection strings and internal paths.
        """
        logger.exception("unhandled error while serving a request")
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ApiError.INTERNAL_ERROR,
            "An internal error occurred. Quote the request_id when reporting it.",
        )
