"""Auth logic. No `Request`/`Response`, no cookies — those are an HTTP-layer detail.

As a result the same code serves a CLI, background jobs and unit tests.
"""

import asyncio
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.core.domain.errors import AuthError
from app.core.domain.identity import AuthenticatedUser
from app.core.domain.result import Err, Ok, Result
from app.core.domain.roles import Role
from app.core.domain.slug import slugify
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
    waste_time_like_verify,
)
from app.db.client import Database
from app.db.documents import utc_now
from app.db.identifiers import identifier_of, to_object_id, to_text
from app.models.auth import User, UserSession
from app.models.organizations import Membership, Organization
from app.repositories.auth import (
    IdentityRepository,
    OrganizationRepository,
    SessionRepository,
    UserRepository,
)

# We do not write `last_seen_at` on every request — one UPDATE per window.
_LAST_SEEN_REFRESH = timedelta(minutes=15)
_SLUG_ATTEMPTS = 5
# Two attempts are enough: the first slug collision is accidental, a second one after adding
# a random suffix would already be implausible.
_REGISTRATION_ATTEMPTS = 2


def _violated_unique_field(error: DuplicateKeyError) -> str | None:
    """Which unique index blew up — the email or the organization slug."""
    key_pattern = (error.details or {}).get("keyPattern") or {}
    return next(iter(key_pattern), None)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime
    user: AuthenticatedUser


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.users = UserRepository()
        self.sessions = SessionRepository()
        self.organizations = OrganizationRepository()
        self.identity = IdentityRepository()

    async def register(
        self, email: str, password: str, organization_name: str
    ) -> Result[IssuedSession, AuthError]:
        normalized = normalize_email(email)
        if await self.users.get_by_email(normalized) is not None:
            # Fast path: a clean error without attempting a write. This is NOT a safeguard —
            # there is a race between this check and the insert, caught below.
            # TODO(auth): once email verification lands, return a generic "check your inbox"
            # so accounts cannot be enumerated through registration.
            return Err(AuthError.EMAIL_TAKEN)

        # Hashing the password costs ~40 ms of CPU (on a thread), while finding a free slug is
        # I/O — nothing connects them, so they run concurrently. TaskGroup, not gather: it
        # propagates exceptions.
        async with asyncio.TaskGroup() as tasks:
            password_task = tasks.create_task(hash_password(password))
            slug_task = tasks.create_task(self._unique_slug(organization_name))
        password_hash, slug = password_task.result(), slug_task.result()

        # Two attempts, because the only real safeguard is the unique indexes, not the check
        # above. An email collision is final (the account exists); a slug collision is
        # accidental — then we draw a new one and try once more.
        for attempt in range(_REGISTRATION_ATTEMPTS):
            try:
                return Ok(
                    await self._create_account(normalized, password_hash, organization_name, slug)
                )
            except DuplicateKeyError as duplicate:
                field = _violated_unique_field(duplicate)
                if field == "email":
                    return Err(AuthError.EMAIL_TAKEN)
                if field != "slug" or attempt + 1 == _REGISTRATION_ATTEMPTS:
                    raise
                slug = await self._unique_slug(organization_name, force_suffix=True)

        raise AssertionError("unreachable: the loop either returns or raises")  # pragma: no cover

    async def _create_account(
        self, email: str, password_hash: str, organization_name: str, slug: str
    ) -> IssuedSession:
        """Four documents in one transaction: without it a failed write would leave a user
        without an organization, or an organization without an owner.

        NOTE: inside a transaction the operations run SEQUENTIALLY — a Mongo client session
        is not safe for concurrent queries.
        """

        async def write(session: AsyncClientSession) -> IssuedSession:
            user = await self.users.add(
                User(email=email, password_hash=password_hash), session=session
            )
            organization = await self.organizations.add(
                Organization(name=organization_name.strip(), slug=slug), session=session
            )
            await self.identity.add_membership(
                Membership(
                    user_id=identifier_of(user),
                    organization_id=identifier_of(organization),
                    role=Role.OWNER,
                ),
                session=session,
            )
            return await self._issue_session(identifier_of(user), email, session=session)

        return await self.db.in_transaction(write)

    async def login(self, email: str, password: str) -> Result[IssuedSession, AuthError]:
        normalized = normalize_email(email)
        user = await self.users.get_by_email(normalized)
        if user is None:
            # Constant response time: a missing account must not be faster than a wrong
            # password.
            await waste_time_like_verify(password)
            return Err(AuthError.INVALID_CREDENTIALS)

        ok, updated_hash = await verify_password(password, user.password_hash)
        if not ok:
            return Err(AuthError.INVALID_CREDENTIALS)
        if not user.is_active:
            return Err(AuthError.ACCOUNT_DISABLED)
        if updated_hash is not None:
            # argon2 parameters changed — migrate the hash while the user is signing in.
            # This is NOT a user-initiated password change, so sessions stay valid.
            await self.users.set_password_hash(user, updated_hash)

        return Ok(await self._issue_session(identifier_of(user), user.email))

    async def logout(self, token: str) -> None:
        await self.sessions.delete_by_token_hash(hash_session_token(token))

    async def resolve_session(self, token: str) -> Result[AuthenticatedUser, AuthError]:
        now = utc_now()
        idle_cutoff = now - timedelta(hours=self.settings.session_idle_timeout_hours)
        user_session = await self.sessions.get_unexpired(
            hash_session_token(token), now, idle_cutoff
        )
        if user_session is None:
            return Err(AuthError.SESSION_INVALID)

        # Hot path: the frontend calls this on every page entry. The user document and their
        # organizations depend only on `user_id` from the session, so they run concurrently —
        # four database round trips become three.
        async with asyncio.TaskGroup() as tasks:
            user_task = tasks.create_task(self.users.get_by_id(user_session.user_id))
            organizations_task = tasks.create_task(
                self.identity.organizations_for_user(user_session.user_id)
            )
        user = user_task.result()
        if user is None:
            return Err(AuthError.SESSION_INVALID)
        if not user.is_active:
            await self.sessions.delete_for_user(identifier_of(user))
            return Err(AuthError.ACCOUNT_DISABLED)

        if now - user_session.last_seen_at > _LAST_SEEN_REFRESH:
            await self.sessions.touch(user_session, now)

        return Ok(
            AuthenticatedUser(
                id=to_text(identifier_of(user)),
                email=user.email,
                organizations=organizations_task.result(),
            )
        )

    async def change_password(self, user_id: str, new_password: str) -> None:
        """Changing the password invalidates ALL of the user's sessions.

        The `delete_for_user` docstring declared this contract from the start, but nothing
        implemented it. Without this a stolen cookie survives a password reset — meaning the
        reset does not revoke access, which is its only job.
        """
        identifier = to_object_id(user_id)
        if identifier is None:
            return
        password_hash = await hash_password(new_password)

        async def rotate(session: AsyncClientSession) -> None:
            user = await self.users.get_by_id(identifier, session=session)
            if user is None:
                return
            await self.users.set_password_hash(user, password_hash, session=session)
            await self.sessions.delete_for_user(identifier, session=session)

        await self.db.in_transaction(rotate)

    async def delete_user(self, user_id: str) -> None:
        """Deletes the account together with its related data.

        Mongo has no `ON DELETE CASCADE`, so the cascade lives here — explicitly and inside a
        transaction. Every new document pointing at a user must be added to this method.
        """

        identifier = to_object_id(user_id)
        if identifier is None:
            # A malformed identifier deletes nothing; it is not an error worth an exception.
            return

        async def purge(session: AsyncClientSession) -> None:
            await self.sessions.delete_for_user(identifier, session=session)
            await self.identity.delete_memberships_for_user(identifier, session=session)
            user = await self.users.get_by_id(identifier, session=session)
            if user is not None:
                await user.delete(session=session)

        await self.db.in_transaction(purge)

    async def _issue_session(
        self, user_id: PydanticObjectId, email: str, session: AsyncClientSession | None = None
    ) -> IssuedSession:
        token = generate_session_token()
        now = utc_now()
        expires_at = now + timedelta(hours=self.settings.session_ttl_hours)
        await self.sessions.add(
            UserSession(
                user_id=user_id,
                token_hash=hash_session_token(token),
                expires_at=expires_at,
                last_seen_at=now,
            ),
            session=session,
        )
        # Session ceiling: we add the newest one, then delete the oldest ones above the limit.
        # Done AFTER the write so the limit counts the session just issued.
        await self.sessions.delete_oldest_for_user(
            user_id, self.settings.max_sessions_per_user, session=session
        )

        return IssuedSession(
            token=token,
            expires_at=expires_at,
            user=await self._authenticated_user(user_id, email, session=session),
        )

    async def _authenticated_user(
        self, user_id: PydanticObjectId, email: str, session: AsyncClientSession | None = None
    ) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=to_text(user_id),
            email=email,
            organizations=await self.identity.organizations_for_user(user_id, session=session),
        )

    async def _unique_slug(self, organization_name: str, *, force_suffix: bool = False) -> str:
        base = slugify(organization_name)
        if not force_suffix and not await self.organizations.slug_exists(base):
            return base
        for _ in range(_SLUG_ATTEMPTS):
            candidate = f"{base}-{secrets.token_hex(3)}"
            if not await self.organizations.slug_exists(candidate):
                return candidate
        # Colliding 5 times in a row is unrealistic; an explicit failure beats silent
        # overwriting.
        raise RuntimeError("could not generate a unique organization slug")
