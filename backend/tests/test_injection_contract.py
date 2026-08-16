"""Injection: NoSQL, server-side JS and whatever comes back to the browser.

Mongo has no SQL, so "SQL injection" does not exist — but it has two variants of its own:

1. **Operator injection.** `{"email": {"$ne": null}}` in a JSON body reaches the filter as an
   operator rather than a value. Sign-in without knowing the password. The defence is
   structural: input fields are scalars, so Pydantic rejects a dict before anyone builds a
   filter. We test BOTH sides: the schema level and an actual HTTP payload.
2. **Server-side JavaScript.** `$where`, `$function`, `$accumulator` and `mapReduce` execute
   JS inside `mongod`. With user data in the mix that is remote code execution in the
   database. We use none of them and this file keeps it that way.

The third part is XSS: we check that input travels through the system unmangled and comes
back as **data** (JSON + `nosniff`) rather than as a document to render — and that values
derived from input (the slug that lands in a URL) have a forced safe alphabet.
"""

import inspect
import typing
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import BaseModel, ValidationError

from app.schemas import auth as auth_schemas
from app.schemas.auth import StrictRequest

SOURCE_DIR = Path(__file__).resolve().parent.parent / "src" / "app"

# Operators that execute JavaScript inside the database server.
FORBIDDEN_MONGO_OPERATORS = ("$where", "$function", "$accumulator", "map_reduce", "mapReduce")


def _python_sources() -> list[Path]:
    return sorted(SOURCE_DIR.rglob("*.py"))


def _request_models() -> list[type[BaseModel]]:
    return [
        member
        for _, member in inspect.getmembers(auth_schemas, inspect.isclass)
        if issubclass(member, BaseModel) and member.__name__.endswith("Request")
    ]


def test_server_side_javascript_operators_are_absent() -> None:
    """`$where` with user input appended is code execution inside `mongod`.

    We have no use for them — an index serves every query we need — so the ban is total and
    requires no case-by-case "is it safe this time" judgement.
    """
    offenders = {
        str(path.relative_to(SOURCE_DIR)): operator
        for path in _python_sources()
        for operator in FORBIDDEN_MONGO_OPERATORS
        if operator in path.read_text(encoding="utf-8")
    }
    assert not offenders, (
        f"operators executing JavaScript in the database: {offenders}. The query can be "
        "written with declarative operators ($eq, $in, $gt) — those execute no code."
    )


@pytest.mark.parametrize("model", _request_models(), ids=lambda m: m.__name__)
def test_request_models_forbid_unknown_fields(model: type[BaseModel]) -> None:
    """`extra='forbid'` closes mass assignment: a field the schema does not know is an error."""
    assert issubclass(model, StrictRequest), (
        f"{model.__name__} must inherit from StrictRequest — otherwise unknown fields pass "
        "silently."
    )
    assert model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("model", _request_models(), ids=lambda m: m.__name__)
@pytest.mark.parametrize("hostile", [{"$ne": None}, {"$gt": ""}, ["a"], {"$regex": ".*"}], ids=repr)
def test_no_request_field_accepts_a_mongo_operator(model: type[BaseModel], hostile: object) -> None:
    """The heart of the operator-injection defence — and the reason we do not filter characters.

    Checked by behaviour rather than by annotation introspection: what matters is what Pydantic
    actually **accepts**. A `str` field rejects `{"$ne": null}` before the value reaches a
    repository; a `dict[str, Any]` field would accept it, and a filter built from such a value
    would sign somebody in without knowing the password.

    We submit only the field under test — the rest report as `missing`, which does not bother
    us; we want an error on exactly that field and specifically NOT of the "missing" kind.
    """
    for field_name in model.model_fields:
        try:
            model.model_validate({field_name: hostile})
        except ValidationError as failure:
            rejected = [
                error
                for error in failure.errors()
                if error["loc"] == (field_name,) and error["type"] != "missing"
            ]
        else:
            rejected = []

        assert rejected, (
            f"{model.__name__}.{field_name} accepted `{hostile!r}` — a document containing a "
            "Mongo operator passed validation. The field has to be a scalar."
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"email": {"$ne": None}, "password": {"$ne": None}},
        {"email": {"$gt": ""}, "password": "correct-horse-battery-staple"},
        {"email": ["a@b.c"], "password": "correct-horse-battery-staple"},
    ],
)
async def test_operator_injection_on_login_is_rejected(
    client: AsyncClient, csrf: typing.Callable[[], dict[str, str]], payload: dict[str, object]
) -> None:
    """The NoSQL classic: `{"$ne": null}` matches every document.

    Without scalar field types that is a sign-in to any account without knowing the password.
    """
    response = await client.post("/api/auth/login", json=payload, headers=csrf())
    assert response.status_code == 422, response.text


async def test_unknown_field_in_payload_is_rejected(
    client: AsyncClient, csrf: typing.Callable[[], dict[str, str]]
) -> None:
    """Mass assignment: `is_admin` added to registration has to be an error, not silence."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "mass@example.com",
            "password": "correct-horse-battery-staple",
            "organization_name": "Mass Assignment",
            "is_admin": True,
        },
        headers=csrf(),
    )
    assert response.status_code == 422


async def test_operator_like_characters_in_password_still_work(
    client: AsyncClient, csrf: typing.Callable[[], dict[str, str]]
) -> None:
    """Positive control: we do **not** filter characters, only the shape of the data.

    The password `{"$ne": null}` as text is a valid password and must work at sign-in. A
    character blacklist would break password managers and could be bypassed anyway.
    """
    tricky_password = '{"$ne": null} || 1==1 <script>'
    email = "tricky@example.com"

    register = await client.post(
        "/api/auth/register",
        json={"email": email, "password": tricky_password, "organization_name": "Tricky Org"},
        headers=csrf(),
    )
    assert register.status_code == 201, register.text

    await client.post("/api/auth/logout", headers=csrf())
    login = await client.post(
        "/api/auth/login",
        json={"email": email, "password": tricky_password},
        headers=csrf(),
    )
    assert login.status_code == 200, login.text


async def test_html_payload_survives_as_data_and_never_as_markup(
    client: AsyncClient, csrf: typing.Callable[[], dict[str, str]]
) -> None:
    """An organization name containing `<script>` is the classic stored XSS.

    Three conditions at once:
    * the value comes back **unmodified** (escaping is the renderer's job, not the database's —
      otherwise the same value ends up double-escaped in an email and in a CSV),
    * the response is `application/json` with `nosniff`, so the browser will not render it,
    * the slug — the only value DERIVED from input and placed in a URL — has a forced
      `[a-z0-9-]` alphabet.
    """
    payload_name = "<script>alert(1)</script>"
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "xss@example.com",
            "password": "correct-horse-battery-staple",
            "organization_name": payload_name,
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text

    organization = response.json()["organizations"][0]
    assert organization["name"] == payload_name
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert organization["slug"] == "script-alert-1-script"


async def test_control_characters_are_stripped_from_names(
    client: AsyncClient, csrf: typing.Callable[[], dict[str, str]]
) -> None:
    """Invisible characters in a name mean impersonation and corrupted logs.

    `\\u202e` (RIGHT-TO-LEFT OVERRIDE) reverses the display of the rest of the line — a name
    can pretend to be a completely different one. `\\u0000` terminates a string in more than
    one C library.
    """
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "control@example.com",
            "password": "correct-horse-battery-staple",
            # Written as escapes on purpose: these characters are invisible in an editor, and
            # NUL would break the Python parser itself.
            "organization_name": "Acme\u202e\u0000 Corp",
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text

    name = response.json()["organizations"][0]["name"]
    assert name == "Acme Corp"
    assert not any(ord(character) < 0x20 for character in name)


def test_no_dynamic_code_execution_in_sources() -> None:
    """`eval`/`exec` on input arriving over HTTP is code execution inside the app process.

    This project has no use for them, so a ban is simpler than an audit.
    """
    offenders = {
        str(path.relative_to(SOURCE_DIR))
        for path in _python_sources()
        if any(call in path.read_text(encoding="utf-8") for call in ("eval(", "exec("))
    }
    assert not offenders, f"dynamic code execution: {offenders}"


def test_the_operator_guard_would_catch_a_permissive_field() -> None:
    """A control on the detector itself: a model with a `dict` field MUST fail it.

    Without this the test above could quietly check nothing (e.g. if `model_fields` returned
    an empty mapping) and still be green.
    """

    class Permissive(StrictRequest):
        query: dict[str, object]

    with pytest.raises(AssertionError, match="accepted"):
        test_no_request_field_accepts_a_mongo_operator(Permissive, {"$ne": None})
