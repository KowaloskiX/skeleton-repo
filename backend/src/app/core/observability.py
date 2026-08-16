"""Request correlation and log format.

Without a request identifier a production log is a list of sentences with no subject: you can
see that something broke, but not reconstruct one user's sequence of events nor tie a support
report to a log line. So every request gets an `X-Request-Id`, the same identifier comes back
in the response, and it lands on **every** log record produced by that request.

This is the correlation minimum, not full observability. Metrics and traces will arrive
through an internal package (`docs/conventions/06-observability.md`) — we deliberately do not
reach for `opentelemetry` directly here.
"""

import json
import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-Id"

# The identifier goes into logs and into the response, so a value from outside must be narrow:
# a newline would allow appending forged lines to the log (log injection), and a very long
# value would bloat every record.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes `logging` puts on every record. Anything beyond them was added by the caller
# (`logger.info(..., extra={...})`) and we want to see it in the JSON output.
_STANDARD_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "asctime",
    "message",
    "taskName",
}


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to the record. A filter rather than a formatter — it works for every
    output format."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """One line = one JSON object. No external library, because this is all we need."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and key != "request_id"
        }
        if extras:
            # `default=str` instead of blowing up on a UUID or a datetime: logging must never
            # be the cause of a 500.
            payload["extra"] = extras

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, json_format: bool, level: int = logging.INFO) -> None:
    """Sets the handler and format on the root logger.

    Called from `create_app` so log configuration travels with application configuration
    rather than with module import — import-time side effects break tests and scripts.
    """
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if json_format
        # Locally readability in a terminal matters, not parsability.
        else logging.Formatter("%(levelname)-8s %(name)s [%(request_id)s] %(message)s")
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class RequestIdMiddleware:
    """Plain ASGI: the identifier has to exist before anything logs, so this must be the
    outermost layer — including error logs from other middleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _incoming_request_id(scope)
        current = incoming or uuid.uuid4().hex
        token = request_id.set(current)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, current)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id.reset(token)


def _incoming_request_id(scope: Scope) -> str | None:
    """We accept an identifier from outside (a proxy or the frontend often sets one), but only
    in a safe shape — see `_SAFE_REQUEST_ID`."""
    for name, value in scope.get("headers", ()):
        if name.lower() != REQUEST_ID_HEADER.lower().encode():
            continue
        candidate = value.decode("latin-1")
        return candidate if _SAFE_REQUEST_ID.match(candidate) else None
    return None
