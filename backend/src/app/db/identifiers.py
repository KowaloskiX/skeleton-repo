"""Translation between the database identifier type and the rest of the system.

`ObjectId` may not travel further than the persistence layer: the domain is forbidden from
importing `bson`/`pymongo` (`domain_agnostic` in `.importlinter`), and the API contract must not
expose the shape of whichever database happens to be underneath. So identifiers become strings
at this boundary, and this module is the only place that knows both sides.

The parsing direction matters for security, not just for types: an identifier arriving from a
client is untrusted input, and `to_object_id` answers "is this even an identifier" before any
query is built.
"""

from beanie import Document, PydanticObjectId


def to_text(identifier: PydanticObjectId) -> str:
    """Database identifier -> the 24-character hex string the API exposes."""
    return str(identifier)


def to_object_id(value: str) -> PydanticObjectId | None:
    """Client string -> a database identifier, or `None` when it is not one.

    Returns `None` rather than raising: a malformed identifier in a URL is an ordinary 404, not
    an exception. Letting `bson.errors.InvalidId` escape would turn a typo into a 500.
    """
    if not PydanticObjectId.is_valid(value):
        return None
    return PydanticObjectId(value)


def identifier_of(document: Document) -> PydanticObjectId:
    """The identifier of a document that exists in the database.

    Beanie types `id` as optional because a model instance is valid before it is inserted. Every
    document reaching this function has already been written or read back, so `None` here is a
    bug in our code rather than a state a caller should handle — hence a loud failure instead of
    an optional return that would spread through every signature.
    """
    if document.id is None:  # pragma: no cover - unreachable for a persisted document
        raise RuntimeError(f"{type(document).__name__} has no identifier — it was never inserted")
    return document.id
