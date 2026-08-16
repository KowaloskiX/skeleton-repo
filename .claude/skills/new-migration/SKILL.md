---
name: new-migration
description: Change the shape of stored data, add an index or a collection validator. Use when a document gains, loses or renames a field, or when a query needs a new index.
---

# Change data safely

Mongo has no schema, which removes the migration but **not** the compatibility problem: during a
rollout two versions of the code read the same documents.

## Which case is this

| Change | What to do |
|---|---|
| A new field | Nothing — give it a default and old documents read fine. This is the freedom Mongo was chosen for. |
| A new index | Declare it in the document's `Settings.indexes`, then `uv run ensure-indexes` as a release step. |
| Moving/splitting/deriving a field | A Beanie migration in `backend/migrations/`, expand-contract. |
| Dropping a field | Only after every reader has shipped. Separate step, separate deploy. |

## Expand-contract, three deploys

1. **Expand** — add the new field with a default, write both. Old code keeps working.
2. **Backfill** — a Beanie migration in `backend/migrations/`, run once.
3. **Contract** — stop reading the old field, then drop it.

## The migration file

```python
# migrations/20260816_120000_split_user_name.py
from beanie import iterative_migration

from app.models.auth import User


class Forward:
    @iterative_migration()
    async def split_full_name(self, input_document: User, output_document: User) -> None: ...


class Backward:
    @iterative_migration()
    async def merge_names(self, input_document: User, output_document: User) -> None: ...
```

**A `Backward` class is mandatory** — `docs/conventions/04` requires reversibility and Mongo will
not enforce it for you.

```bash
uv run beanie migrate --uri "$MONGODB_URL" --database "$MONGODB_DATABASE" -p migrations
```

## Indexes and validators

Both are applied by the same deployment step, **before** traffic reaches the new instances:

```bash
uv run ensure-indexes
```

On dev the application does it at startup; on staging/prod it does not, because building an
index on a large collection eats I/O.

The `$jsonSchema` validators are generated from the models (`app/db/validation.py`) and check
presence plus BSON type of top-level fields. `additionalProperties` stays allowed on purpose:
expand-contract needs a new field to be writable before the validator that knows about it ships.

## Do not forget

- A new document goes into `app/documents.py`.
- A new field that is required with no default breaks every existing document.
- `tests/test_collection_validation.py` proves the validator accepts what the model writes — run
  it after changing a document.
