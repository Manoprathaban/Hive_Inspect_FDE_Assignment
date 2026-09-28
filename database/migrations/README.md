# database/migrations

Conventions for PostgreSQL schema migrations targeting **local PostgreSQL, Supabase, and CI**.

> Status: **foundation only.** The template schema itself is intentionally deferred to a
> later phase. This directory documents the convention that migrations must follow.

## Rules

1. One file per migration, named with a zero-padded sequence:

   ```
   0001_create_template_schema.sql
   0002_add_template_metadata.sql
   ```

2. Plain SQL only. No tool-specific syntax or secrets. Use the SQL dialect supported by
   both local PostgreSQL and Supabase (RDS-compatible PostgreSQL).

3. Idempotency/migration tracking:
   - Prefer `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`, or
   - Track applied migrations in a `schema_migrations` table and apply in order.

4. Schema `public` is available in all three environments. Name objects with a clear
   prefix if they are specific to Hive Inspect (e.g. `hive_`).

## Applying migrations

Because the files are plain SQL, the same commands apply everywhere:

Local PostgreSQL:

```bash
psql "$DATABASE_URL" -f database/migrations/0001_create_template_schema.sql
```

Supabase (via the connection string from the Supabase dashboard — either direct or
connection pooler URL):

```bash
psql "$DATABASE_URL" -f database/migrations/0001_create_template_schema.sql
# or, when the supabase CLI is available:
supabase db push          # executes the files staged under supabase/migrations
```

CI/CD: run the same `psql -f` loop over `database/migrations/*.sql` in order against a
temporary PostgreSQL service container (see `.github/workflows/ci.yml`).

## Seeds

Fixture/minimal seed data is not implementation code; see `database/seed/README.md`.