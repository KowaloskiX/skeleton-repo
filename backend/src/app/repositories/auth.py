"""Mongo queries for auth. No business rules.

Every method takes an optional `session` — without it a write would fall outside the
transaction opened by the service.
"""

from datetime import datetime

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from app.core.domain.identity import OrganizationRef
from app.db.identifiers import identifier_of, to_text
from app.models.auth import User, UserSession
from app.models.organizations import Membership, Organization
from app.repositories.base import bounded_to_list


class UserRepository:
    async def get_by_email(
        self, email: str, session: AsyncClientSession | None = None
    ) -> User | None:
        return await User.find_one(User.email == email, session=session)

    async def get_by_id(
        self, user_id: PydanticObjectId, session: AsyncClientSession | None = None
    ) -> User | None:
        return await User.get(user_id, session=session)

    async def add(self, user: User, session: AsyncClientSession | None = None) -> User:
        return await user.insert(session=session)

    async def set_password_hash(
        self, user: User, password_hash: str, session: AsyncClientSession | None = None
    ) -> None:
        await user.set({User.password_hash: password_hash}, session=session)


class SessionRepository:
    async def add(
        self, user_session: UserSession, session: AsyncClientSession | None = None
    ) -> UserSession:
        return await user_session.insert(session=session)

    async def get_unexpired(
        self,
        token_hash: str,
        now: datetime,
        idle_cutoff: datetime,
        session: AsyncClientSession | None = None,
    ) -> UserSession | None:
        """Two conditions: absolute TTL and inactivity.

        Filtering on `expires_at` is necessary despite the TTL index, because Mongo deletes
        lazily (a pass roughly every 60 s), so an expired document may linger for a while.
        `last_seen_at` closes ASVS V7 — TTL alone at 14 days meant a cookie from an abandoned
        laptop stayed alive for two weeks despite zero activity.
        """
        return await UserSession.find_one(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > now,
            UserSession.last_seen_at > idle_cutoff,
            session=session,
        )

    async def count_for_user(
        self, user_id: PydanticObjectId, session: AsyncClientSession | None = None
    ) -> int:
        return await UserSession.find(UserSession.user_id == user_id, session=session).count()

    async def delete_oldest_for_user(
        self, user_id: PydanticObjectId, keep: int, session: AsyncClientSession | None = None
    ) -> int:
        """Trims a user's sessions down to the `keep` freshest ones.

        Without a ceiling, a script staying within the rate limit mints hundreds of thousands
        of valid credentials that nobody sees and nobody can revoke in bulk.
        """
        sessions = await bounded_to_list(
            # `-_id` instead of `-created_at`: an ObjectId begins with its creation timestamp,
            # so the primary key already orders by age and no second index is needed.
            UserSession.find(UserSession.user_id == user_id, session=session).sort("-_id"),
            what="user sessions",
        )
        stale = sessions[keep:]
        for user_session in stale:
            await user_session.delete(session=session)
        return len(stale)

    async def touch(
        self, user_session: UserSession, now: datetime, session: AsyncClientSession | None = None
    ) -> None:
        await user_session.set({UserSession.last_seen_at: now}, session=session)

    async def delete_by_token_hash(
        self, token_hash: str, session: AsyncClientSession | None = None
    ) -> None:
        await UserSession.find(UserSession.token_hash == token_hash).delete(session=session)

    async def delete_for_user(
        self, user_id: PydanticObjectId, session: AsyncClientSession | None = None
    ) -> None:
        """Global sign-out — on password change, account lockout and account deletion."""
        await UserSession.find(UserSession.user_id == user_id).delete(session=session)


class OrganizationRepository:
    async def slug_exists(self, slug: str, session: AsyncClientSession | None = None) -> bool:
        return await Organization.find_one(Organization.slug == slug, session=session) is not None

    async def add(
        self, organization: Organization, session: AsyncClientSession | None = None
    ) -> Organization:
        return await organization.insert(session=session)


class IdentityRepository:
    """Identity queries: scoped by `user_id`, not by organization — which is why this
    deliberately does NOT inherit from `TenantScopedRepository` (a user belongs to many
    organizations and must see all of them after signing in)."""

    async def add_membership(
        self, membership: Membership, session: AsyncClientSession | None = None
    ) -> Membership:
        return await membership.insert(session=session)

    async def organizations_for_user(
        self, user_id: PydanticObjectId, session: AsyncClientSession | None = None
    ) -> tuple[OrganizationRef, ...]:
        """Two queries instead of a join.

        Deliberately no `$lookup` aggregation: two simple indexed reads are clearer and faster
        than a pipeline, and a user's organization count is small by nature.
        """
        memberships = await bounded_to_list(
            Membership.find(Membership.user_id == user_id, session=session),
            what="user memberships",
        )
        if not memberships:
            return ()

        role_by_organization = {m.organization_id: m.role for m in memberships}
        organizations = await bounded_to_list(
            Organization.find({"_id": {"$in": list(role_by_organization)}}, session=session).sort(
                "+_id"
            ),
            what="user organizations",
        )
        return tuple(
            OrganizationRef(
                # The domain speaks in strings — see `app.db.identifiers`.
                id=to_text(identifier_of(organization)),
                name=organization.name,
                slug=organization.slug,
                role=role_by_organization[identifier_of(organization)],
            )
            for organization in organizations
        )

    async def delete_memberships_for_user(
        self, user_id: PydanticObjectId, session: AsyncClientSession | None = None
    ) -> None:
        """Mongo has no cascades — deleting a user must clean up memberships explicitly."""
        await Membership.find(Membership.user_id == user_id).delete(session=session)
