# Data migrations (Mongo)

Mongo has no schema to migrate, so migrations split into two categories with two different
tools. There is no equivalent of `alembic upgrade head` doing both.

## 1. Indexes — `uv run ensure-indexes`

Indexes are the only "DDL" that exists here: uniqueness (`users.email`,
`memberships.user_id+organization_id`), session TTL and tenant-filter performance all rest on
them. The same command also applies the `$jsonSchema` collection validators.

You declare indexes in the document's `Settings.indexes`. On dev/test they are created at
application startup; on staging/prod by an explicit deployment step **before** traffic is let
in:

```bash
uv run ensure-indexes
```

Beanie only creates missing indexes, so the command is idempotent.

## 2. Data — Beanie migrations

Changing the shape of a document (moving a field, splitting it in two, deriving a value) is a
data backfill, not a schema change. Beanie's CLI handles that, and the files live here.

```python
# migrations/20260804_120000_split_user_name.py
from beanie import iterative_migration

from app.models.auth import User


class Forward:
    @iterative_migration()
    async def split_full_name(self, input_document: User, output_document: User) -> None:
        first, _, last = input_document.full_name.partition(" ")
        output_document.first_name = first
        output_document.last_name = last


class Backward:
    @iterative_migration()
    async def merge_names(self, input_document: User, output_document: User) -> None:
        output_document.full_name = f"{input_document.first_name} {input_document.last_name}".strip()
```

```bash
uv run beanie migrate --uri "$MONGODB_URL" --database "$MONGODB_DATABASE" -p migrations
uv run beanie migrate --uri "$MONGODB_URL" --database "$MONGODB_DATABASE" -p migrations --backward
```

## Rules

- **Always write a `Backward` class.** `docs/conventions/04` requires reversibility; Mongo will
  not enforce it for you, so it is review discipline.
- **Expand-contract applies just the same.** No schema does not mean no compatibility problem:
  for a while two versions of the code run against the same documents. First add the new field
  and read both, then backfill, and only then stop reading the old one and drop it in a
  separate step.
- **A new field needs no migration** — documents without it are read by Pydantic with the
  default value. That is the main convenience we chose Mongo for; do not spoil it by adding
  required fields with no default.
- **Add a new document to `app/documents.py`**, otherwise Beanie will not register it.
