"""Session and CSRF cookies — the only place that sets them.

Split out of the router because three different routes need the same flags (`HttpOnly`,
`Secure`, `SameSite`), and letting them drift apart between endpoints is a silent security hole.
"""

from datetime import datetime

from fastapi import Request, Response

from app.core.config import Settings
from app.core.csrf import csrf_token_is_valid, issue_csrf_token
from app.services.auth import IssuedSession


def set_csrf_cookie(
    response: Response, settings: Settings, session_token: str | None = None
) -> None:
    """The token is signed and bound to the session — see `app.core.csrf`.

    The cookie is knowingly readable by JavaScript (the client has to echo it in a header), so
    the signature is the only thing defending against a value planted from a subdomain.
    """
    response.set_cookie(
        settings.effective_csrf_cookie_name,
        issue_csrf_token(settings.auth_secret, session_token),
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_hours * 3600,
    )


def ensure_csrf_cookie(request: Request, response: Response, settings: Settings) -> None:
    """Issue a token when there is none **or when it does not match the current session**.

    The "does not match" case is not theoretical: the token is bound to the session, so once
    that session expires (or the user signs in from another tab) the old token stops passing
    and EVERY mutation gets a 403 — without this replacement the application could not recover
    other than by clearing cookies manually.

    We deliberately do not rotate on every GET: that would break concurrent requests (one
    overwrites the cookie while the other is already in flight with the old value).
    """
    session_token = request.cookies.get(settings.session_cookie_name)
    current = request.cookies.get(settings.effective_csrf_cookie_name)
    if csrf_token_is_valid(current, secret=settings.auth_secret, session_token=session_token):
        return
    set_csrf_cookie(response, settings, session_token)


def set_session_cookie(
    response: Response, settings: Settings, token: str, expires_at: datetime
) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        expires=expires_at,
    )


def apply_session(response: Response, settings: Settings, issued: IssuedSession) -> None:
    set_session_cookie(response, settings, issued.token, issued.expires_at)
    # A privilege-level change means rotating the CSRF token (session fixation defence).
    # The new token is immediately bound to the NEW session.
    set_csrf_cookie(response, settings, issued.token)


def clear_session_cookie(response: Response, settings: Settings) -> None:
    # The attributes must match those in `set_session_cookie` — otherwise in production we
    # respond with a non-Secure cookie of the same name.
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    # We rotate the CSRF token rather than delete it — otherwise the login form would have to
    # fetch a new one first after signing out. The new token goes back to the anonymous binding.
    set_csrf_cookie(response, settings, None)
