# database/seed

Conventions for static/reference data loaded after migrations.

> Status: **foundation only.** No seed data defined yet.

## Rules

1. One file per seed, plain SQL, named by content (or sequence when ordering matters):

   ```
   reference_data.sql
   demo_templates.sql
   ```

2. Seeds must be re-runnable — prefer `ON CONFLICT DO NOTHING` / `ON CONFLICT DO UPDATE`.

3. Seeds may reference the sample templates in `../sample-data` when a template importer
   exists (deferred to a later phase). Until then this directory stays mostly empty.

## Applying seeds

Identical to migrations — `psql` against the target database:

```bash
psql "$DATABASE_URL" -f database/seed/reference_data.sql
```