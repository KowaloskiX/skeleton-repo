"""Collection validators — document-shape control that also applies OUTSIDE the application.

Pydantic guards what the application writes. It does not guard a migration script, the Mongo
shell or `mongoimport`. These tests exercise the server-side net: writes that bypass the
application go straight through the driver here, exactly as a human would issue them at
midnight.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from beanie import PydanticObjectId
from pymongo.errors import WriteError

from app.db.client import Database
from app.db.validation import apply_collection_validators, build_json_schema
from app.documents import DOCUMENT_MODELS
from app.models.auth import User, UserSession
from app.models.organizations import Membership


@pytest.fixture
async def validated(database: Database) -> Database:
    await apply_collection_validators(database.database, DOCUMENT_MODELS)
    return database


def _valid_user() -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "_id": PydanticObjectId(),
        "email": "raw@example.com",
        # The validator checks the BSON type, not the contents — this is not a real hash.
        "password_hash": "placeholder-not-a-hash",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


def test_schema_covers_every_field_of_a_document() -> None:
    schema = build_json_schema(User)

    assert schema["properties"]["_id"]["bsonType"] == "objectId", (
        "the identifier type must be pinned: a document written by hand with a string `_id` "
        "would break every reference to it"
    )
    assert schema["properties"]["email"]["bsonType"] == "string"
    assert schema["properties"]["is_active"]["bsonType"] == "bool"
    assert schema["properties"]["created_at"]["bsonType"] == "date"
    assert set(schema["required"]) == set(schema["properties"])


def test_enum_field_is_described_as_string() -> None:
    """`Role` is a `StrEnum` — in the database it is a plain string, not an object."""
    assert build_json_schema(Membership)["properties"]["role"]["bsonType"] == "string"


def test_reference_fields_are_pinned_to_the_identifier_type() -> None:
    """A reference stored as a string would never match a query built from an ObjectId, and the
    mismatch is invisible: the query simply returns nothing."""
    schema = build_json_schema(Membership)

    assert schema["properties"]["user_id"]["bsonType"] == "objectId"
    assert schema["properties"]["organization_id"]["bsonType"] == "objectId"


def test_tenant_field_is_required() -> None:
    """A missing `organization_id` means a document invisible to the tenant filter — data no
    user will ever see, yet which still occupies space."""
    assert "organization_id" in build_json_schema(Membership)["required"]


async def test_valid_document_passes(validated: Database) -> None:
    """Positive control: the validator must not get in the way of correct writes."""
    result = await validated.database["users"].insert_one(_valid_user())
    assert result.inserted_id is not None


async def test_document_with_a_wrong_type_is_rejected(validated: Database) -> None:
    """A date stored as a string is a migration-script classic — and a silent bug, because
    range queries on dates stop returning that document."""
    document = _valid_user() | {"created_at": "2026-08-15"}

    with pytest.raises(WriteError, match="validation"):
        await validated.database["users"].insert_one(document)


async def test_document_with_a_missing_field_is_rejected(validated: Database) -> None:
    document = _valid_user()
    del document["password_hash"]

    with pytest.raises(WriteError, match="validation"):
        await validated.database["users"].insert_one(document)


async def test_typo_in_a_field_name_is_caught(validated: Database) -> None:
    """A typo does not silently create a new field — the real one is then missing."""
    document = _valid_user()
    document["e_mail"] = document.pop("email")

    with pytest.raises(WriteError, match="validation"):
        await validated.database["users"].insert_one(document)


async def test_extra_field_is_allowed(validated: Database) -> None:
    """We deliberately do NOT block extra fields.

    Expand-contract requires a new field to be writable before we ship a validator that knows
    about it. Beanie also adds fields of its own (`revision_id`).
    """
    result = await validated.database["users"].insert_one(_valid_user() | {"new_field": 1})
    assert result.inserted_id is not None


async def test_application_writes_still_work_under_validation(validated: Database) -> None:
    """The most important control: a validator built from a model must accept a document
    serialized by that same model. A mismatch here would block production."""
    session = UserSession(
        user_id=PydanticObjectId(),
        token_hash="a" * 64,
        expires_at=datetime.now(UTC),
    )
    await session.insert()

    assert await validated.database["user_sessions"].find_one({"_id": session.id}) is not None


async def test_validators_are_idempotent(database: Database) -> None:
    """The deployment step runs on every release — a second invocation must not fail."""
    first = await apply_collection_validators(database.database, DOCUMENT_MODELS)
    second = await apply_collection_validators(database.database, DOCUMENT_MODELS)

    assert not [name for name, state in first.items() if state.startswith("ERROR")]
    assert not [name for name, state in second.items() if state.startswith("ERROR")]
