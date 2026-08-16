"""Collection `$jsonSchema` validators — the last line of defence for document shape.

Pydantic guards writes **from the application**. It guards nothing that comes in beside it:
a migration script, the Mongo shell, `mongoimport`, another microservice sharing the same
connection string. A collection validator lives on the server, so it applies to every write.

**The scope is deliberately narrow** — we check presence and BSON type of top-level fields.
That catches real mistakes (a typo in a field name, a date stored as a string, a missing
`organization_id`) without trying to recreate all of Pydantic inside the database:
`$jsonSchema` is a subset of JSON Schema draft-4, with no `$ref`, no formats and no custom
validators. Duplicating business rules there would end in two sources of truth that drift.

`additionalProperties` stays **allowed**: Beanie adds fields of its own (e.g. `revision_id`),
and expand-contract requires a new field to be writable before the new validator ships.
"""

import datetime
import logging
from enum import Enum
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin
from uuid import UUID

from bson import ObjectId
from pydantic.fields import FieldInfo
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

# Python type -> `bsonType`. Deliberately no `float`: Mongo stores `double`, but an integer
# supplied as a float would land there too — numeric mapping is spelled out below instead.
# Order matters: the first matching entry wins, so subclasses come before their bases.
_BSON_TYPES: dict[type, str] = {
    # Before `str`: `PydanticObjectId` subclasses `ObjectId`, and both would otherwise match a
    # more generic entry further down.
    ObjectId: "objectId",
    str: "string",
    bool: "bool",
    UUID: "binData",
    datetime.datetime: "date",
    dict: "object",
    list: "array",
}

# `int` separately: Mongo distinguishes 32- and 64-bit integers, Pydantic does not — allow both.
_INT_BSON_TYPES = ["int", "long"]


def _unwrap(annotation: Any) -> Any:
    """Strips `Annotated[...]`, leaving the actual type."""
    return get_args(annotation)[0] if get_origin(annotation) is Annotated else annotation


def _bson_types(annotation: Any) -> list[str] | None:
    """The list of allowed `bsonType`s, or `None` when the type cannot be mapped.

    `None` means "skip this field" — a validator that guesses is worse than no validator: it
    would reject correct writes and nobody would trust it.
    """
    annotation = _unwrap(annotation)
    origin = get_origin(annotation)

    if origin in (Union, UnionType):
        collected: list[str] = []
        for argument in get_args(annotation):
            if argument is type(None):
                collected.append("null")
                continue
            nested = _bson_types(argument)
            if nested is None:
                return None
            collected.extend(nested)
        return list(dict.fromkeys(collected))

    if origin is not None:
        annotation = origin

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        # Our enums are `StrEnum` — in the database they are plain strings.
        return ["string"] if issubclass(annotation, str) else None

    if annotation is int:
        return list(_INT_BSON_TYPES)

    if isinstance(annotation, type):
        for python_type, bson_type in _BSON_TYPES.items():
            if issubclass(annotation, python_type):
                return [bson_type]

    return None


def _is_required(field: FieldInfo) -> bool:
    """Required = a field whose absence is an error.

    Beanie serializes the **whole** model, so fields with defaults always end up in the
    document too. We require their presence — that is exactly what catches a document written
    by hand next to the application. Optional fields (`X | None`) allow `null`, but the key
    must be there.
    """
    return not field.exclude


def build_json_schema(document: type[Any]) -> dict[str, Any]:
    """Builds the `$jsonSchema` for a single Beanie document."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    skipped: list[str] = []

    for name, field in document.model_fields.items():
        # Beanie maps `id` onto `_id`; `revision_id` and helper fields are left alone.
        key = "_id" if name == "id" else (field.alias or name)
        if key == "revision_id":
            continue

        bson_types = _bson_types(field.annotation)
        if bson_types is None:
            skipped.append(name)
            continue

        if key == "_id":
            # Beanie types `id` as optional because a model is valid before insertion, but a
            # stored document always has one — allowing null here would weaken the check for
            # the single field Mongo guarantees.
            bson_types = [t for t in bson_types if t != "null"]

        properties[key] = {"bsonType": bson_types[0] if len(bson_types) == 1 else bson_types}
        if _is_required(field):
            required.append(key)

    if skipped:
        logger.info(
            "validator for collection %s skips fields with unmappable types: %s",
            document.get_settings().name,
            ", ".join(skipped),
        )

    return {"bsonType": "object", "required": required, "properties": properties}


async def apply_collection_validators(
    database: AsyncDatabase[dict[str, Any]], documents: tuple[type[Any], ...]
) -> dict[str, str]:
    """Creates or updates the validator on every collection. Returns `name -> outcome`.

    A deployment step, not an application-startup side effect — same as indexes.
    """
    results: dict[str, str] = {}
    existing = set(await database.list_collection_names())

    for document in documents:
        name = document.get_settings().name
        schema = build_json_schema(document)
        try:
            if name in existing:
                await database.command(
                    "collMod", name, validator={"$jsonSchema": schema}, validationAction="error"
                )
                results[name] = "updated"
            else:
                await database.create_collection(
                    name, validator={"$jsonSchema": schema}, validationAction="error"
                )
                results[name] = "created"
        except OperationFailure as error:  # pragma: no cover - depends on cluster permissions
            # On Atlas `collMod` requires the `dbAdmin` role. Missing permissions must not fail
            # the deployment — the application works without the validator, just without that
            # safety net.
            logger.error("could not set the validator for %s: %s", name, error)
            results[name] = f"ERROR: {error.code}"

    return results
