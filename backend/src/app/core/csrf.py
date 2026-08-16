"""CSRF via a **signed** double-submit cookie.

Plain double-submit (a random token in a cookie compared against a header) has a known hole:
an attacker able to set a cookie on a parent domain — a hijacked subdomain, a preview
environment, XSS on `blog.example.com` — overwrites `csrf_token` with their own value and
sends a matching header. `SameSite=Lax` does not help, because a subdomain is **same-site**,
so the session cookie is sent as usual. On duplicate names Starlette takes the last
occurrence, which is the attacker's fresher cookie.

That is why the token is **HMAC-signed** with `AUTH_SECRET` and **bound to the session**.
The attacker does not know the secret, so they cannot forge the signature, and a token cut
from their own session will not pass in somebody else's. The `__Host-` prefix (over HTTPS)
closes the same vector on the browser side — both layers are cheap, so we keep both.

Token format: `<random_value>.<hmac_sha256(secret, value + ":" + binding)>`
"""

import hashlib
import hmac
import secrets

_TOKEN_BYTES = 32
_SEPARATOR = "."
# Binding for requests without a session (the login and registration forms — no session yet).
_ANONYMOUS_BINDING = "anonymous"


def _signature(secret: str, value: str, binding: str) -> str:
    payload = f"{value}:{binding}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def session_binding(session_token: str | None) -> str:
    """What the CSRF token is bound to.

    Deliberately a hash rather than the raw session token: the signature travels to the
    browser in a cookie readable by JavaScript, so it must not allow reconstructing the
    session credential.
    """
    if not session_token:
        return _ANONYMOUS_BINDING
    return hashlib.sha256(session_token.encode()).hexdigest()


def issue_csrf_token(secret: str, session_token: str | None = None) -> str:
    value = secrets.token_urlsafe(_TOKEN_BYTES)
    binding = session_binding(session_token)
    return f"{value}{_SEPARATOR}{_signature(secret, value, binding)}"


def csrf_token_is_valid(token: str | None, *, secret: str, session_token: str | None) -> bool:
    """Whether the token is ours and matches the CURRENT session.

    Used in two places: when checking a mutating request, and when issuing the cookie (a token
    bound to a stale session has to be replaced, otherwise the client keeps getting 403 until
    somebody clears cookies by hand).
    """
    if not token:
        return False

    value, separator, provided_signature = token.partition(_SEPARATOR)
    if not separator or not value or not provided_signature:
        return False

    binding = session_binding(session_token)
    expected = _signature(secret, value, binding)
    if secrets.compare_digest(provided_signature.encode(), expected.encode()):
        return True

    # A token issued before login is bound to "anonymous". The login form sends it together
    # with a session cookie only when the user already had an old session — hence we also
    # accept the anonymous binding, but never the binding of SOMEBODY ELSE'S session.
    anonymous = _signature(secret, value, _ANONYMOUS_BINDING)
    return secrets.compare_digest(provided_signature.encode(), anonymous.encode())


def csrf_token_matches(
    cookie_token: str | None,
    header_token: str | None,
    *,
    secret: str,
    session_token: str | None = None,
) -> bool:
    """Three conditions at once: cookie == header, signature valid, binding matches.

    Comparison on BYTES: `secrets.compare_digest` on strings requires ASCII, and Starlette
    decodes headers as latin-1 — any byte >= 0x80 raised `TypeError`, which turned into a 500
    with a traceback instead of a proper 403.
    """
    if not cookie_token or not header_token:
        return False
    if not secrets.compare_digest(cookie_token.encode("utf-8"), header_token.encode("utf-8")):
        return False
    return csrf_token_is_valid(cookie_token, secret=secret, session_token=session_token)
