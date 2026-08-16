"""Auth request/response schemas. Input validation at the HTTP boundary."""

import unicodedata
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.domain.roles import Role

# ASVS 5.0 V6: minimum 8 characters, no upper bound below 64.
# 12 as a deliberately stricter product default.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
# The same limit as on the document (`app.models.auth.EMAIL_MAX_LENGTH`) — mismatched limits
# at the boundary and in the database mean one layer rejects what the other accepted.
MAX_EMAIL_LENGTH = 320
MIN_ORGANIZATION_NAME_LENGTH = 2
MAX_ORGANIZATION_NAME_LENGTH = 120


class StrictRequest(BaseModel):
    """Base for input: trims whitespace and rejects unknown fields.

    `extra="forbid"` is deliberate — a typo in a field name should be a 422, not a silently
    ignored field that somebody assumes was saved.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _normalize_text(value: str) -> str:
    """NFKC plus removal of control and format characters.

    Without it `"\u200b\u200b"` (two zero-width spaces) passes as a two-character organization
    name, and a name starting with a Cyrillic A (U+0410) impersonates the Latin "Acme" — when
    inviting people to an organization that is a ready-made impersonation vector.
    """
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) not in {"Cc", "Cf"}).strip()


class RegisterRequest(StrictRequest):
    email: Annotated[EmailStr, Field(max_length=MAX_EMAIL_LENGTH)]
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    organization_name: str = Field(
        min_length=MIN_ORGANIZATION_NAME_LENGTH, max_length=MAX_ORGANIZATION_NAME_LENGTH
    )

    @field_validator("organization_name")
    @classmethod
    def _normalize_organization_name(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if len(normalized) < MIN_ORGANIZATION_NAME_LENGTH:
            raise ValueError(
                f"Organization name must contain at least {MIN_ORGANIZATION_NAME_LENGTH} "
                "visible characters."
            )
        return normalized


class LoginRequest(StrictRequest):
    email: Annotated[EmailStr, Field(max_length=MAX_EMAIL_LENGTH)]
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class OrganizationSummary(BaseModel):
    # A string rather than a dedicated type: the database identifier stops at the persistence
    # layer (see `app.db.identifiers`), and the API contract should not name whichever database
    # produced it.
    id: str
    name: str
    slug: str
    role: Role


class CurrentUserResponse(BaseModel):
    id: str
    email: str
    organizations: list[OrganizationSummary]


class SessionResponse(BaseModel):
    """Response of `GET /api/auth/session` — `user: null` means "not signed in"."""

    user: CurrentUserResponse | None


class MessageResponse(BaseModel):
    message: str
