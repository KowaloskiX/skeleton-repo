"""An organization is a tenant. First-class from day one (PLAN section 4)."""

from typing import ClassVar

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import Field

from app.core.domain.roles import Role
from app.db.documents import TenantOwnedMixin, TimestampMixin

NAME_MAX_LENGTH = 120
SLUG_MAX_LENGTH = 64


class Organization(TimestampMixin, Document):
    name: str = Field(max_length=NAME_MAX_LENGTH)
    slug: str = Field(max_length=SLUG_MAX_LENGTH)

    class Settings:
        name: ClassVar[str] = "organizations"
        indexes: ClassVar[list[pymongo.IndexModel]] = [
            pymongo.IndexModel([("slug", 1)], unique=True, name="uq_organizations_slug")
        ]


class Membership(TimestampMixin, TenantOwnedMixin, Document):
    """Assignment of a user to an organization with a role (RBAC scoped per-org)."""

    user_id: PydanticObjectId
    role: Role

    class Settings:
        name: ClassVar[str] = "memberships"
        indexes: ClassVar[list[pymongo.IndexModel]] = [
            # One membership per user + organization pair.
            pymongo.IndexModel(
                [("user_id", 1), ("organization_id", 1)],
                unique=True,
                name="uq_memberships_user_organization",
            ),
            # Required by the tenancy contract: every tenant filter goes through this field.
            pymongo.IndexModel([("organization_id", 1)], name="ix_memberships_organization_id"),
        ]
