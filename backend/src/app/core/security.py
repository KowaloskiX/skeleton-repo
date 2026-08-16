"""Auth cryptography: passwords (argon2id) and session tokens. No HTTP, no database.

**Why the public API is `async` even though crypto does no I/O.** argon2 is deliberately
expensive: measured at ~40 ms of pure CPU per hash and per verification. Called directly
inside an `async def` it blocks the **entire** event loop — 20 concurrent logins serialized
into ~1.6 s, and an innocent `/api/health` degraded 29-fold. That is why the blocking
variants are private (impossible to call by accident) and the public ones offload to threads.

**Why a semaphore rather than plain `to_thread`.** Two reasons:
1. argon2id is memory-hard — 64 MiB per call. anyio's default pool has 40 slots, i.e. up to
   ~2.5 GiB at peak: trading a CPU stall for memory exhaustion.
2. argon2 has **its own** parallelism (`parallelism=4`), so every hash occupies 4 CPU
   threads. Running 8 at once on 8 cores starves the event-loop thread.

Limit = `cores / parallelism`. Measured on 8 cores, 20 verifications:

| limit | total time | MAX loop lag |
|------:|-----------:|-------------:|
|     1 |     838 ms |       1.9 ms |
|     2 |     661 ms |       4.4 ms |
|     4 |     617 ms |      10.4 ms |
|     8 |     767 ms |      57.5 ms |

A limit of 2 (= 8/4) gives near-best throughput at negligible lag — hence the formula.
"""

import hashlib
import os
import secrets

from anyio import CapacityLimiter, to_thread
from pwdlib import PasswordHash

_SESSION_TOKEN_BYTES = 32

# argon2id with pwdlib's recommended defaults (64 MiB, time_cost 3).
# `verify_and_update` lets us migrate old hashes during login.
_hasher = PasswordHash.recommended()

# Hash compared against when the user does not exist — equalizes response time
# and blocks account enumeration by timing.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-compare")

# The `parallelism` parameter from pwdlib's recommended settings. Kept as a constant because
# it feeds the limit formula; if pwdlib ever changes it,
# `test_argon2_parallelism_matches_assumption` will complain.
_ARGON2_PARALLELISM = 4

_HASHING_LIMITER = CapacityLimiter(max(1, (os.cpu_count() or 1) // _ARGON2_PARALLELISM))


def _hash_password_blocking(password: str) -> str:
    return _hasher.hash(password)


def _verify_password_blocking(password: str, password_hash: str) -> tuple[bool, str | None]:
    return _hasher.verify_and_update(password, password_hash)


def _waste_time_blocking(password: str) -> None:
    _hasher.verify(password, _DUMMY_HASH)


async def hash_password(password: str) -> str:
    return await to_thread.run_sync(_hash_password_blocking, password, limiter=_HASHING_LIMITER)


async def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Returns (is_valid, new_hash_if_rehash_needed)."""
    return await to_thread.run_sync(
        _verify_password_blocking, password, password_hash, limiter=_HASHING_LIMITER
    )


async def waste_time_like_verify(password: str) -> None:
    """Call this when the account does not exist — otherwise a missing account gives itself
    away through a shorter response.

    It goes through the same semaphore as a real verification: if the "no such account" path
    queued separately, response times would start telling the two cases apart again.
    """
    await to_thread.run_sync(_waste_time_blocking, password, limiter=_HASHING_LIMITER)


def generate_session_token() -> str:
    return secrets.token_urlsafe(_SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """SHA-256 is enough: the token carries 256 bits of entropy, so brute force is off the
    table (argon2 would only add cost to every request). Cheap, so it stays synchronous."""
    return hashlib.sha256(token.encode()).hexdigest()
