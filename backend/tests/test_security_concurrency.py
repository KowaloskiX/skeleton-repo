"""Crypto concurrency contract — argon2 must not block the event loop.

This is a regression test for a specific, measured defect: argon2 costs ~40 ms of CPU, so
calling it directly inside an `async def` freezes the **whole** application for the duration
of the hash. Measured before the fix: 20 concurrent logins serialized into ~1.6 s, and
`/api/health` degraded 29-fold.

The assertions are **relative** (threads vs inline) rather than millisecond thresholds —
otherwise the test would depend on machine speed and flake on shared CI runners.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from pwdlib.hashers.argon2 import Argon2Hasher

from app.core import security


async def _count_loop_ticks(
    work: Callable[[], Awaitable[None]], tick: float = 0.005
) -> tuple[int, float]:
    """Runs `work` while counting how often the event loop got to service a monitor.

    Returns (tick count, largest delay in ms). Few ticks = the loop was blocked.
    """
    lags: list[float] = []
    stop = asyncio.Event()

    async def monitor() -> None:
        while not stop.is_set():
            started = time.perf_counter()
            await asyncio.sleep(tick)
            lags.append((time.perf_counter() - started - tick) * 1000)

    monitor_task = asyncio.create_task(monitor())
    await asyncio.sleep(0.05)  # let the monitor warm up
    before = len(lags)
    await work()
    stop.set()
    await monitor_task

    during = lags[before:]
    return len(during), max(during, default=0.0)


async def test_hashing_yields_to_event_loop_unlike_inline_call() -> None:
    """The point: the threaded version must yield to the loop more often than the inline one."""
    password_hash = await security.hash_password("correct-horse-battery-staple")
    repeats = 8

    async def inline() -> None:
        for _ in range(repeats):
            security._verify_password_blocking("wrong-password", password_hash)

    async def threaded() -> None:
        await asyncio.gather(
            *[security.verify_password("wrong-password", password_hash) for _ in range(repeats)]
        )

    inline_ticks, inline_lag = await _count_loop_ticks(inline)
    threaded_ticks, threaded_lag = await _count_loop_ticks(threaded)

    assert threaded_ticks > inline_ticks, (
        f"hashing does not release the loop: threaded {threaded_ticks} ticks, "
        f"inline {inline_ticks}. Did someone swap the async crypto API for a blocking call?"
    )
    assert threaded_lag < inline_lag, (
        f"MAX loop lag did not drop: threaded {threaded_lag:.0f} ms, inline {inline_lag:.0f} ms"
    )


def test_argon2_parallelism_matches_assumption() -> None:
    """The hashing concurrency limit = cores / argon2 `parallelism`.

    If pwdlib changed its recommended parameters, the formula would stop fitting and would need
    re-measuring — hence we check it rather than take the constant on faith.
    """
    actual = Argon2Hasher()._hasher.parallelism
    assert actual == security._ARGON2_PARALLELISM, (
        f"argon2 now reports parallelism={actual} while the limit formula assumes "
        f"{security._ARGON2_PARALLELISM}. Re-measure the table in security.py's docstring."
    )


def test_hashing_concurrency_is_bounded() -> None:
    """Without a limit, anyio's 40 threads times argon2's 64 MiB peak at ~2.5 GiB."""
    assert security._HASHING_LIMITER.total_tokens >= 1
    assert security._HASHING_LIMITER.total_tokens <= 8


async def test_public_crypto_api_is_async_only() -> None:
    """The blocking variants are private — the public ones must be coroutines.

    If somebody "simplified" the API into a synchronous version, the defect would come back
    quietly.
    """
    for name in ("hash_password", "verify_password", "waste_time_like_verify"):
        assert asyncio.iscoroutinefunction(getattr(security, name)), (
            f"{name} must be async — otherwise it blocks the event loop"
        )
