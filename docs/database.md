# Database

The app uses the [Tortoise ORM](https://tortoise.github.io) over
[asyncpg](https://magicstack.github.io/asyncpg/current/) against [Postgres 18](https://www.postgresql.org),
with [Aerich](https://github.com/tortoise/aerich) for migrations. Postgres does more work here than usual:
it also backs the cache, the job queue, full-text search, and — through
[pgvector](https://github.com/pgvector/pgvector) — vector search.

---

## Changing the schema

1. Add, edit, or remove model code in `app.models`. A new model *module* also needs registering in
   `tortoise_config` in `config/settings.py`, or its tables won't be discovered.
2. Generate the migration: `make db_migrate ARGS="--name add_widgets"`. It lands in
   `migrations/{model_package}/{id}_{timestamp}_{name}.py` — read it before trusting it.
3. Apply it: `make db_upgrade`.
4. Exercise the change in the app.

Use `make db_migrate_empty ARGS="--name backfill_widgets"` when you need a migration Aerich can't derive —
a data backfill, a concurrent index, anything hand-written. `make db_downgrade` reverts the last one.

Commit migrations in the same change as the models they came from. CI regenerates migrations and fails if
that produces a diff, so a model change without its migration won't merge. Migrations run against the
database before the new code is deployed, which is what makes them a compatibility contract: a migration
has to leave the *currently running* code working.

Data backfills belong in migrations rather than scripts — a deployment has no way to run
`make script`.

## Layering

Models are layered like the rest of the app, and the import linter enforces it:
workspaces → collaboration → accounts. A workspace model may import from collaboration; the reverse is a
lint failure. Models also avoid depending on each other within a layer — see
[architecture](architecture.md), and use a presenter when two models seem to need each other.

## Local databases

`make db_create` creates the database for the current checkout and brings it up to date;
`make db_reset` drops and recreates it. Both derive the database name from the checkout directory, so
several clones coexist — see [development](development.md#running-multiple-instances).

`make db_console` opens psql against the current checkout's database. `make db_dump ARGS="> dump.sql"`
dumps it.

`make db_create` assumes the current OS user has permission to create databases, which is how Postgres is
usually set up locally. If yours isn't, or you want to point at a database somewhere else, set
`POSTGRES_URL` in `.env.secrets`:

```
POSTGRES_URL=asyncpg://user:password@localhost:5432/custom_database
```

`AUXILIARY_POSTGRES_URL` configures a second connection when you need one.

## Seed data

`make db_seed` populates the database with realistic scenarios. See [seeds](seeds.md).

## Test databases

The test database is upgraded automatically by the `make test` targets, so its schema always matches your
models. `make server` deliberately doesn't do this — your development data is not disposable. See
[testing](testing.md).
