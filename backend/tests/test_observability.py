"""Request correlation: the identifier in the response, in the logs, and injection-proof."""

import json
import logging
import sys

import pytest
from httpx import AsyncClient

from app.core.observability import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    request_id,
)

VALID_INCOMING_ID = "trace-abc_123"


async def test_every_response_carries_a_request_id(client: AsyncClient) -> None:
    """Without it, a report of "sign-in did not work at 14:32" has no way into the log."""
    response = await client.get("/api/health")
    assert response.headers[REQUEST_ID_HEADER]


async def test_ids_differ_between_requests(client: AsyncClient) -> None:
    first = (await client.get("/api/health")).headers[REQUEST_ID_HEADER]
    second = (await client.get("/api/health")).headers[REQUEST_ID_HEADER]
    assert first != second


async def test_incoming_id_is_reused(client: AsyncClient) -> None:
    """A proxy or the frontend assigns the identifier earlier — overwriting it would break the
    trail exactly where it is needed most."""
    response = await client.get("/api/health", headers={REQUEST_ID_HEADER: VALID_INCOMING_ID})
    assert response.headers[REQUEST_ID_HEADER] == VALID_INCOMING_ID


@pytest.mark.parametrize(
    "hostile",
    [
        "abc\ndef",  # log injection: a line of the attacker's own in the log
        "abc\r\nSet-Cookie: session=x",  # header splitting
        "x" * 200,  # bloating every log record
        "id with spaces",
        "",
    ],
)
async def test_hostile_incoming_id_is_replaced_not_echoed(
    client: AsyncClient, hostile: str
) -> None:
    """The outside value lands in logs and in the response header, so the shape is narrow.

    A newline would allow appending a crafted line to the log — for instance one that looks
    like somebody else's successful sign-in.
    """
    response = await client.get("/api/health", headers=[(b"x-request-id", hostile.encode())])

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != hostile
    assert returned.isalnum(), "a generated identifier must be plain hex"


def test_log_records_get_the_current_request_id() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "anything", None, None)
    token = request_id.set("my-identifier")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id.reset(token)

    assert record.__dict__["request_id"] == "my-identifier"


def test_json_formatter_emits_one_parsable_object_per_line() -> None:
    """A log collector reads line by line — a multi-line record falls apart into garbage."""
    record = logging.LogRecord("app.auth", logging.WARNING, __file__, 7, "failed %s", ("X",), None)
    # Through `__dict__`, because that is exactly what `logging` does with `extra=` fields —
    # and typeshed does not know about attributes added at runtime.
    record.__dict__["request_id"] = "abc123"
    record.__dict__["user_id"] = "u-1"

    line = JsonFormatter().format(record)
    assert "\n" not in line

    payload = json.loads(line)
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "app.auth"
    assert payload["message"] == "failed X"
    assert payload["request_id"] == "abc123"
    assert payload["extra"]["user_id"] == "u-1"


def test_json_formatter_survives_unserializable_extras() -> None:
    """Logging must never be the cause of a 500 — an unserializable object goes out as `str`."""

    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    record = logging.LogRecord("app", logging.INFO, __file__, 1, "x", None, None)
    record.__dict__["thing"] = Opaque()

    assert json.loads(JsonFormatter().format(record))["extra"]["thing"] == "<opaque>"


def test_json_formatter_includes_the_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord("app", logging.ERROR, __file__, 1, "failed", None, exc_info)
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_configure_logging_replaces_handlers(capsys: pytest.CaptureFixture[str]) -> None:
    """Idempotence: two calls must not produce two copies of every line."""
    configure_logging(json_format=True)
    configure_logging(json_format=True)

    logging.getLogger("app.probe").info("one line")
    lines = [line for line in capsys.readouterr().err.splitlines() if "one line" in line]
    assert len(lines) == 1
