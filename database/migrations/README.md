# database/migrations

Conventions for PostgreSQL schema migrations targeting **local PostgreSQL, Supabase, and CI**.

## Files

| Migration | Contents |
| --- | --- |
| `0001_create_template_schema.sql` | Types (enums), tables, constraints, indexes, `updated_at` trigger, guarded Supabase Auth→`public.users` sync trigger |
| `0002_rls_policies.sql` | Row Level Security enablement + ownership policies (applies only when the `auth` schema exists; no-op on plain PostgreSQL) |

Apply once, in order, to an empty database. Requires PostgreSQL ≥ 13 (`gen_random_uuid()` is
built-in from 13). Future migrations continue the `NNNN_description.sql` sequence.

## Rules

1. One file per migration, named with a zero-padded sequence: `0001_...`, `0002_...`.
2. Plain SQL only — no tool-specific syntax, no secrets. Dialect must run on both local
   PostgreSQL and Supabase PostgreSQL.
3. Supabase-only pieces (RLS, `auth.users` sync) are guarded by an `auth`-schema check so
   every migration is valid on plain local/CI PostgreSQL.
4. Migrations are applied **once, in order, to an empty database** (the bootstrap path used
   by local dev, Supabase, and CI). Never hand-edit a live database outside a migration.

## Applying migrations

```bash
# local PostgreSQL / Supabase (connection string from the Supabase dashboard)
psql "$DATABASE_URL" -f database/migrations/0001_create_template_schema.sql
psql "$DATABASE_URL" -f database/migrations/0002_rls_policies.sql
```

On Supabase you can also paste each file into the SQL editor. CI/CD runs the same
`psql -f` loop over `database/migrations/*.sql` in numeric order against a temporary
PostgreSQL service container.

## Seeds

Fixture/minimal seed data is not implementation code; see `database/seed/README.md`.
The only seed is the deterministic development identity (`database/seed/dev_auth.sql`).