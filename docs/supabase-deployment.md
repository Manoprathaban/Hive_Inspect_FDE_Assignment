# Supabase Database Deployment Runbook

Apply the Hive Inspect database schema to a **Supabase project** (managed PostgreSQL).

Exactly two files deploy, in this order:

| Order | File | What it does |
| --- | --- | --- |
| 1 | `database/migrations/0001_create_template_schema.sql` | Enums, tables, constraints, indexes, `updated_at` triggers, guarded Supabase Auth → `public.users` mirror trigger |
| 2 | `database/migrations/0002_rls_policies.sql` | Enables Row Level Security and creates owner-scoped policies (only on Supabase, where the `auth` schema exists) |

Nothing else deploys. In particular **`database/seed/dev_auth.sql` is development-only and must NEVER be applied to production** — production `public.users` rows are created automatically by the `on_auth_user_created` trigger when a Supabase Auth user signs up.

## Prerequisites

1. A Supabase project (created from the Supabase dashboard).
2. Either:
   - the **SQL Editor** (dashboard → **SQL Editor** → **New query**) — no CLI or credentials beyond project login, or
   - a **connection string**: dashboard → **Settings → Database → Connection string** → copy the **Session pooler (transaction mode)** PostgreSQL URI for `psql`/CLI use.

The migration files are plain, dialect-compatible PostgreSQL (nothing Supabase-specific is required for them to parse correctly); `gen_random_uuid()` is built into PostgreSQL 13+ and is pre-available on Supabase.

## Method A — Supabase SQL Editor (recommended, no CLI)

1. Open the project, go to **SQL Editor → New query**.
2. Paste the full contents of `database/migrations/0001_create_template_schema.sql`, click **Run**.
3. Paste the full contents of `database/migrations/0002_rls_policies.sql`, click **Run**.
4. Confirm both reported success, then run the verification section below.

Both statements are wrapped in `BEGIN; ... COMMIT;`, so each file either applies fully or not at all.

## Method B — `psql` / Supabase CLI

### B1. Direct `psql` (connection string)

```bash
DATABASE_URL="postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"

psql "$DATABASE_URL" -f database/migrations/0001_create_template_schema.sql
psql "$DATABASE_URL" -f database/migrations/0002_rls_policies.sql
```

### B2. Supabase CLI `db push`

`supabase db push` only tracks migrations under `supabase/migrations/`. Either set that up as a one-time baseline, or skip it and use the SQL Editor / B1:

```bash
supabase init
supabase link --project-ref <project-ref>
cp database/migrations/0001_create_template_schema.sql supabase/migrations/
cp database/migrations/0002_rls_policies.sql supabase/migrations/
supabase db push
```

Prefer A or B1 unless you intend to maintain all future migrations through the CLI.

## Post-deploy verification

Run these in the SQL Editor. All should return the expected results:

```sql
-- 1) Tables exist
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
-- expect: comment_options, comments, import_issues, items, sections, templates, users

-- 2) RLS is enabled on every user-owned table
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND rowsecurity = true;
-- expect 7 rows: comment_options, comments, import_issues, items, sections, templates, users

-- 3) RLS policies were created (one per table, all *_owner_all / users_self)
SELECT tablename, policyname
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;

-- 4) The Auth sync trigger is attached to auth.users
SELECT tgname, event_object_schema, event_object_table
FROM pg_trigger
WHERE tgname = 'on_auth_user_created';
-- expect 1 row on auth.users

-- 5) updated_at triggers exist on the five mutable tables
SELECT event_object_table::text AS tbl, count(*) AS triggers
FROM pg_trigger
WHERE tgname = 'users_set_updated_at'
   OR tgname = 'templates_set_updated_at'
   OR tgname = 'sections_set_updated_at'
   OR tgname = 'items_set_updated_at'
   OR tgname = 'comments_set_updated_at'
GROUP BY event_object_table::text
ORDER BY 1;
-- expect one row each for users, templates, sections, items, comments

-- 6) Smoke test identity mirror: sign up a user in Authentication → Users,
--    then the row appears here with no manual insert:
SELECT id FROM public.users;
```

### Live behavior check (optional but recommended)

1. In **Authentication → Users**, create a test user (or confirm an existing one).
2. Confirm `public.users` gained a row automatically (the `on_auth_user_created` trigger).
3. Create a template row as that user and confirm you cannot read it as a different user without RLS bypassing (the backend also enforces the same `owner_id` scoping, so this is defense in depth).

## Notes and limitations

- If Supabase Auth users already exist at deploy time, the trigger only mirrors **new** signups. Backfill existing users with one statement:
  ```sql
  INSERT INTO public.users (id)
  SELECT a.id FROM auth.users a ON CONFLICT (id) DO NOTHING;
  ```
- `database/seed/dev_auth.sql` (the `00000000-0000-0000-0000-000000000001` dev identity) must not be applied in production; it exists only for the local development stub.
- The migrations target an empty database and are applied once, in order. There are no down-migrations yet; the schema is additive.
- Pre-deploy validation against a fresh local PostgreSQL runs the same files plus the suite in `database/tests/` (migrations, behavior, RLS/ownership). Run it locally before deploying:
  ```bash
  cd database && pip install -r requirements-tests.txt && pytest
  ```