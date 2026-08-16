---
name: query-mongo
description: Query MongoDB by hand — from mongosh, a script or an ad-hoc pymongo session — without scanning a collection. Use whenever you need to look at stored data, count documents, check what a query would return, or debug something against the database.
---

# Query Mongo without scanning it

An ad-hoc query is written once and forgotten; the collection it runs against grows for years.
Everything below exists so a debugging session cannot become the incident.

## Connect

```bash
docker compose exec -T db mongosh \
  "mongodb://app:app@localhost:27017/?directConnection=true&authSource=admin" --quiet --eval '…'
```

`authSource=admin` is not optional — the user is created in `admin`, and without it the
connection fails with a bare `Authentication failed` that reads like a wrong password.

**Before touching anything shared, ask which database.** On a local container the answer is
obvious; against a staging or production cluster it never is, and the read-only assumption is
yours to confirm, not to infer from the collection name.

## Look before you query

```javascript
db.users.estimatedDocumentCount()   // O(1), reads collection metadata
db.users.getIndexes()               // what you are allowed to filter and sort on
```

**Never `countDocuments({})` to see how big a collection is.** It walks the whole collection or
index to produce an exact number nobody needed. `estimatedDocumentCount()` answers from metadata
in constant time. Use `countDocuments` only with a selective filter, and only when the exact
number matters.

## Then query

Three rules, in order of how much damage they prevent:

1. **Filter only on indexed fields.** `getIndexes()` told you which. A filter on anything else is
   a collection scan.
2. **Always `.limit()`.** You are reading to understand, not to export. Ten documents answer
   almost every question.
3. **Project what you need.** `find(filter, {email: 1, created_at: 1})` — a document can be large
   and you rarely want all of it. Never return `password_hash` or `token_hash` to a terminal.

```javascript
db.users.find({email: "someone@example.com"}, {email: 1, created_at: 1}).limit(10)
```

**Sorting needs an index too.** An unindexed sort happens in memory with a 32 MB ceiling and
fails outright above it. Identifiers here are `ObjectId`, whose leading bytes are a timestamp, so
`sort({_id: -1})` is a free "newest first" — reach for that before adding an index on
`created_at`.

**Page with `_id`, not `skip`.** `skip(n)` walks and discards `n` documents every time, so page
500 costs 500 pages of work: `find({_id: {$lt: lastSeenId}}).sort({_id: -1}).limit(20)`.

## Check the plan when it matters

```javascript
db.users.find({email: "x@y.z"}).explain("executionStats").executionStats
```

Read three numbers:

- `nReturned` — what you got.
- `totalDocsExamined` — what the server touched. Close to `nReturned` is healthy; orders of
  magnitude larger means a scan.
- `totalKeysExamined` — index entries read.

The winning stage tells you the same in one word: `IXSCAN`/`EXPRESS_IXSCAN` means an index was
used, **`COLLSCAN` means the whole collection was read**.

## Seatbelts

```bash
cd backend && uv run strict-queries      # notablescan on locally; --off to revert
```

The database then rejects an unindexed query instead of running it — the same guard the test
suite runs under. Turn it on before exploratory work; a mistake becomes an error message rather
than a stalled server.

For a one-off against something bigger, cap the query itself:

```javascript
db.users.find({…}).maxTimeMS(5000)
```

## Never

- A write without a filter. `updateMany({}, …)` and `deleteMany({})` touch every document.
- `$where` or `mapReduce` — they execute JavaScript inside the server, and a repository contract
  forbids them in application code for the same reason.
- Building a filter by pasting a value into a string. Pass it as a value; `{"_id": "<hex>"}` is
  also wrong — an identifier has to be an `ObjectId`, or the query silently matches nothing.
