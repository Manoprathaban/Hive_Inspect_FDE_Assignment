# database/seed

Static/minimal seed data loaded after migrations.

## Files

| Seed | Purpose |
| --- | --- |
| `dev_auth.sql` | **Development-only** deterministic identity (`00000000-0000-0000-0000-000000000001`) matching the backend `DevAuthProvider`. Never apply in production — production rows are created by the `on_auth_user_created` trigger when a Supabase Auth user signs up. |

## Rules

1. One file per seed, plain SQL, named by content (or sequence when ordering matters).
2. Seeds must be re-runnable — prefer `ON CONFLICT DO NOTHING` / `ON CONFLICT DO UPDATE`.
3. No fake template data. The real Spectora template is imported from
   `sample-data/sheet1.xml` by the importer in the next phase; it is not duplicated into
   SQL seed files.

## Applying seeds

```bash
psql "$DATABASE_URL" -f database/seed/dev_auth.sql
```

If you added more seeds, apply them in any order.