"""Creates indexes and collection validators — a deployment step, not a startup side effect.

In Mongo, indexes are the only "DDL" we have: there are no tables or columns to migrate, but
uniqueness, TTL and query performance all rest on them. That is why creating them is an
explicit, deliberately invoked operation — building an index on a large collection eats I/O.

On top of that come the `$jsonSchema` validators (see `app.db.validation`): the only check on
document shape that also covers writes from outside the application — a migration script, the
Mongo shell, `mongoimport`.

Run with: `uv run ensure-indexes`
"""

from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict

from app.core.config import get_settings
from app.db.client import Database
from app.db.validation import apply_collection_validators
from app.documents import DOCUMENT_MODELS


class EnsureIndexes(BaseSettings):
    """CLI settings (pydantic-settings instead of argparse — typed and validated)."""

    model_config = SettingsConfigDict(cli_parse_args=True)

    async def cli_cmd(self) -> None:
        settings = get_settings()
        database = Database.from_settings(settings)
        try:
            await database.init_documents(DOCUMENT_MODELS, create_indexes=True)
            validators = await apply_collection_validators(database.database, DOCUMENT_MODELS)
            for model in DOCUMENT_MODELS:
                name = model.get_settings().name
                indexes = await database.database[name].index_information()
                print(f"{name}: {', '.join(sorted(indexes))}")
                print(f"{name}: validator {validators.get(name, 'skipped')}")
        finally:
            await database.dispose()


def main() -> None:
    CliApp.run(EnsureIndexes)


if __name__ == "__main__":
    main()
