"""Auth documents.

Neither the user nor the session is tenant-owned — a user can belong to many organizations.
"""

from datetime import datetime
from typing import ClassVar

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import Field

from app.db.documents import TimestampMixin, utc_now

EMAIL_MAX_LENGTH = 320  # RFC 5321: 64 (local part) + @ + 255 (domain)
TOKEN_HASH_LENGTH = 64  # sha256 hex


class User(TimestampMixin, Document):
    # The email is stored normalized (lowercase) — uniqueness without case-sensitivity traps.
    email: str = Field(max_length=EMAIL_MAX_LENGTH)
    password_hash: str
    is_active: bool = True

    class Settings:
        name: ClassVar[str] = "users"
        indexes: ClassVar[list[pymongo.IndexModel]] = [
            pymongo.IndexModel([("email", 1)], unique=True, name="uq_users_email")
        ]


class UserSession(TimestampMixin, Document):
    """A server-side session. Only the token hash is stored — a database leak yields no
    ready-to-use cookies. The document can be deleted, i.e. a session revoked instantly."""

    user_id: PydanticObjectId
    token_hash: str = Field(min_length=TOKEN_HASH_LENGTH, max_length=TOKEN_HASH_LENGTH)
    expires_at: datetime
    last_seen_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name: ClassVar[str] = "user_sessions"
        indexes: ClassVar[list[pymongo.IndexModel]] = [
            pymongo.IndexModel([("token_hash", 1)], unique=True, name="uq_sessions_token_hash"),
            pymongo.IndexModel([("user_id", 1)], name="ix_sessions_user_id"),
            # TTL: Mongo removes expired sessions on its own, so no cleanup job is needed.
            # Deletion is lazy (a pass roughly every 60 s), which is why queries STILL filter
            # on `expires_at` — otherwise an expired session would keep working for a minute.
            pymongo.IndexModel(
                [("expires_at", 1)], expireAfterSeconds=0, name="ttl_sessions_expires_at"
            ),
        ]
