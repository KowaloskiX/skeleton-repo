"""Identity of the signed-in user — pure domain, no ORM and no HTTP.

Identifiers are strings here, not the database's id type. `bson.ObjectId` would drag the
persistence layer into the domain, which `domain_agnostic` in `.importlinter` forbids — and
rightly: the rules in this layer should read the same whatever stores the data. Conversion
happens once, in `app.db.identifiers`.
"""

from dataclasses import dataclass

from app.core.domain.roles import Role


@dataclass(frozen=True, slots=True)
class OrganizationRef:
    id: str
    name: str
    slug: str
    role: Role


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: str
    email: str
    organizations: tuple[OrganizationRef, ...]

    def role_in(self, organization_id: str) -> Role | None:
        for org in self.organizations:
            if org.id == organization_id:
                return org.role
        return None
