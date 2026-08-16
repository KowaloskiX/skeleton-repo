"""Turns on `notablescan` on a LOCAL Mongo, so an unindexed query fails instead of scanning.

The test suite already runs with this parameter, which is what keeps missing indexes out of the
repository. This script extends the same guard to manual work: clicking through the UI, a script,
a `mongosh` session. A query with no index then returns `NoQueryExecutionPlans` rather than
quietly reading the whole collection.

It refuses to run against anything that is not local. `notablescan` is a **server-wide** switch —
enabling it on a shared cluster would break every other consumer, and Atlas does not expose
`setParameter` at all. There the equivalent is the Atlas Profiler plus an alert on slow queries.

Run with: `uv run strict-queries` (add `--off` to switch it back).
"""

from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict
from pymongo import AsyncMongoClient

from app.core.config import get_settings

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "@db:", "//db:")


def _is_local(url: str) -> bool:
    return any(host in url for host in _LOCAL_HOSTS)


class StrictQueries(BaseSettings):
    """CLI settings (pydantic-settings instead of argparse — typed and validated)."""

    model_config = SettingsConfigDict(cli_parse_args=True)

    off: bool = False

    async def cli_cmd(self) -> None:
        settings = get_settings()
        if not _is_local(settings.mongodb_url):
            raise SystemExit(
                "MONGODB_URL does not point at a local database. `notablescan` is a server-wide "
                "setting — refusing to change it on a shared cluster."
            )

        client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_url)
        try:
            await client.admin.command({"setParameter": 1, "notablescan": not self.off})
        finally:
            await client.close()

        state = "off" if self.off else "on"
        print(f"notablescan {state}: unindexed queries are {'allowed' if self.off else 'rejected'}")


def main() -> None:
    CliApp.run(StrictQueries)


if __name__ == "__main__":
    main()
