"""Edge middleware: security headers, body size limit, CSRF default-deny.

All three are **middleware** rather than route dependencies, and that is the point: a
dependency has to be remembered on every new route, while middleware covers them
automatically. Same principle as the rate limiter — a new endpoint is protected before anyone
thinks about it.
"""

import logging

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.csrf import csrf_token_matches
from app.core.domain.errors import ApiError
from app.core.errors_http import error_response

logger = logging.getLogger(__name__)

CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# The frontend is same-origin and loads nothing external, so the policy can be narrow.
# `frame-ancestors 'none'` supersedes X-Frame-Options (newer and supports full origins).
# `script-src` keeps `'unsafe-inline'` because TanStack Start injects hydration data as an
# inline `<script>`; there are no event-handler attributes, so styles need no nonce.
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "object-src 'none'"
)

_STATIC_SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": _CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Disable browser APIs we do not use — limits the damage after a hypothetical XSS.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # Kept for old browsers that do not know frame-ancestors.
    "X-Frame-Options": "DENY",
}

# One year, including subdomains. Sent ONLY over HTTPS — the header is ignored on http, and
# sent by accident from a dev machine it can pin localhost to HTTPS in the developer's browser.
_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        super().__init__(app)
        self._send_hsts = settings.cookie_secure

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _STATIC_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if self._send_hsts:
            response.headers.setdefault("Strict-Transport-Security", _HSTS)
        return response


class BodySizeLimitMiddleware:
    """Rejects oversized requests before FastAPI reads them into memory.

    `max_length` on a Pydantic field protects nothing: validation runs only after the whole
    body has been buffered.

    Deliberately **plain ASGI** rather than `BaseHTTPMiddleware`. The latter would need
    `await request.body()` to count bytes of a chunked transfer — that is, buffering the whole
    body just to conclude it is too large. Exactly the memory consumption the limit exists to
    prevent. Here we count bytes inside `receive`, on the fly: the request is cut off the
    moment it crosses the threshold, not after it has been fully received.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # Fast path: a declared size is rejected immediately, without reading a single byte.
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_bytes:
            await _too_large(self._max_bytes)(scope, receive, send)
            return

        received = 0
        exceeded = False
        response_started = False

        async def counting_receive() -> Message:
            """Past the threshold we pretend the client disconnected.

            Deliberately a signal rather than an exception: FastAPI wraps **every** error from
            reading the body into `HTTPException(400, "There was an error parsing the body")`,
            so an exception would never make it back here — the client would get 400 instead
            of 413.
            """
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_bytes:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            # The application is answering a request we have just invalidated — its response
            # (a 400 after the disconnect) goes to the bin; we send our own 413 instead.
            if exceeded:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, counting_receive, guarded_send)

        if exceeded and not response_started:
            logger.warning("request exceeded the %d byte limit mid-transfer", self._max_bytes)
            await _too_large(self._max_bytes)(scope, receive, send)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Default-deny for mutating methods.

    Protection used to be opt-in (`dependencies=[CsrfProtected]` on a route), so the first
    endpoint added without that line would go in unprotected while CI stayed green.
    """

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        settings = self._settings
        cookie_token = request.cookies.get(settings.effective_csrf_cookie_name)
        header_token = _header_value(request.headers, CSRF_HEADER_NAME)
        session_token = request.cookies.get(settings.session_cookie_name)

        if not csrf_token_matches(
            cookie_token,
            header_token,
            secret=settings.auth_secret,
            session_token=session_token,
        ):
            return error_response(403, ApiError.CSRF_INVALID, "Invalid CSRF token.")
        return await call_next(request)


def _header_value(headers: Headers, name: str) -> str | None:
    return headers.get(name)


def _too_large(max_bytes: int) -> JSONResponse:
    return error_response(
        413, ApiError.PAYLOAD_TOO_LARGE, f"Request exceeds the {max_bytes} byte limit."
    )
