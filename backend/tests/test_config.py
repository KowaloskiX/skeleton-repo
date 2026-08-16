"""Configuration is a security contract — these values must not drift silently."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.domain.environments import AppEnv

# A test constant, not a secret: the validator only requires 32 characters or more, so a
# repeated character satisfies it without looking like a credential.
STRONG_SECRET = "a" * 32


@pytest.mark.parametrize("app_env", ["staging", "prod"])
def test_cookies_require_tls_outside_local_envs(app_env: AppEnv) -> None:
    assert Settings(app_env=app_env, auth_secret=STRONG_SECRET).cookie_secure is True


@pytest.mark.parametrize("app_env", ["dev", "test"])
def test_cookies_allow_http_locally(app_env: AppEnv) -> None:
    assert Settings(app_env=app_env).cookie_secure is False


def test_default_connection_targets_local_container() -> None:
    """The default port is 27018, not 27017 — otherwise a locally installed mongod would
    intercept the connection and the application would quietly talk to another database."""
    settings = Settings()
    assert ":27018" in settings.mongodb_url
    # Transactions require a replica set, and that advertises itself by container name.
    assert "directConnection=true" in settings.mongodb_url


@pytest.mark.parametrize("value", ["*", "http://localhost:3000,*", " * "])
def test_wildcard_cors_origin_is_rejected(value: str) -> None:
    """`*` with `allow_credentials=True` makes Starlette reflect any Origin.

    A foreign site could then read the signed-in user's email and organization list. It is the
    reflex fix when "CORS does not work" on a preview environment, so it has to fail at boot.
    """
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(cors_origins=value)


@pytest.mark.parametrize("app_env", ["staging", "prod"])
def test_default_secret_cannot_leave_local_envs(app_env: AppEnv) -> None:
    """CSRF token signatures stand on `auth_secret` — the default value must not ship."""
    with pytest.raises(ValidationError, match="AUTH_SECRET"):
        Settings(app_env=app_env)
    with pytest.raises(ValidationError, match="AUTH_SECRET"):
        Settings(app_env=app_env, auth_secret="too-short")


def test_csrf_cookie_gets_host_prefix_only_with_tls() -> None:
    """`__Host-` forces Secure + Path=/ + no Domain, which closes cookie tossing from a
    subdomain. Over http a browser would reject such a cookie, so locally it is absent."""
    assert Settings(app_env="dev").effective_csrf_cookie_name == "csrf_token"
    assert (
        Settings(app_env="prod", auth_secret=STRONG_SECRET).effective_csrf_cookie_name
        == "__Host-csrf_token"
    )


def test_api_docs_are_local_only() -> None:
    """Swagger in production is a ready-made API manual complete with the error-code
    catalogue."""
    assert Settings(app_env="dev").expose_api_docs is True
    assert Settings(app_env="prod", auth_secret=STRONG_SECRET).expose_api_docs is False
