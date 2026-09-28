# NOTES.md

Working notes / decision log for the Hive Inspect Template Importer assignment.

## 2026-09-28 — Repository bootstrap

- Repository initialized for the *Hive Inspect Template Importer* assignment.
- Scope of this phase: foundation only — structure, tooling, protocols, local dev, CI.
  No product features implemented.
- `sheet1.xml` (Spectora InterNACHI Residential template worksheet export) moved from
  the repo root into `sample-data/` as the canonical sample input.

## Architecture decisions

- **Monolith, not microservices.** One FastAPI service split into clear layers.
- **Protocol-first.** `TemplateImporter` and `TemplateRepository` are the first replaceable
  boundaries. Future boundaries reserved: `ContentProcessor`, `AIService`, `FileStorage`.
- **Dependency direction is enforced by structure, not by a framework:**

  ```
  API → Application → Protocols / Domain → Adapters → Infrastructure
  ```

- Application/domain code must not import FastAPI request objects, XLSX parsing, Supabase
  SDK, asyncpg/SQLAlchemy specifics, or Gemini SDK. Those stay at the edges.
- **Importer plugin architecture.** The application depends on the `TemplateImporter`
  protocol, so a Spectora XLSX importer, a future importer, or a test/mock importer can be
  swapped without touching use cases.
- **Schema foundation decided (this phase).** Real schema implemented:
  `users → templates → sections → items → comments → comment_options`, plus
  `templates → import_issues`. See `docs/DATABASE_DESIGN.md`. Ordering is explicit and
  zero-based (`display_order`). Ownership: `templates.owner_id` scoped in the app layer and
  enforced again by RLS on Supabase (`auth.uid()`-keyed policies in `0002_rls_policies.sql`).
  No profiles table, no template blob, no cached infra.
- **Auth boundary.** `AuthenticationProvider → UserContext → application services`.
  Production: Supabase Auth (provider stub wired later). Development: `DevAuthProvider`
  (deterministic user, seeded by `database/seed/dev_auth.sql`). RLS is never weakened for
  the dev stub.

## Tech stack (locked)

- Frontend: React + TypeScript (Lovable-assisted), independent from the backend.
- Backend: Python, FastAPI, Pydantic, Uvicorn; SQLAlchemy + asyncpg for PostgreSQL later.
- DB: PostgreSQL on Supabase (managed hosting layer only — not the app backend). Schema in
  `database/migrations/` (plain SQL, applied in numeric order).
- AI: Gemini only where it adds real value, always behind a replaceable service boundary.
- Ship: Vercel (frontend), Render (backend), Supabase (DB).

## 2026-09-28 — Schema/database foundation

- Shipped `0001_create_template_schema.sql` (types/tables/constraints/indexes + guarded
  Supabase auth sync trigger), `0002_rls_policies.sql` (RLS, guarded by `auth` schema
  existence), and `database/seed/dev_auth.sql` (dev-only deterministic identity).
- Renamed comment ordering column to `display_order` (zero-based, explicit at every level);
  added non-negative CHECKs on all order fields.
- Measured the real export (392 comments; 13 sections; 61 items; `Order (w/i item)` column
  is EMPTY → importer assigns 0-based first-appearance order; category/defaults/estimates
  mostly absent; photos/location/locked/uses never populated → "unsupported-if-present"
  bucket surfaced through `import_issues`).
- Replaced placeholder domain models with the real aggregate (`Template`/`Section`/`Item`/
  `Comment`/`CommentOption`/`ImportIssue`, `UserContext`) and finalized the repository +
  authentication protocol boundaries. Import-issue listing folded into `TemplateRepository`.
- Decision log: `docs/DATABASE_DESIGN.md` supersedes the older `docs/schema.md` (deleted).

## Open questions

- Next phase: PostgreSQL repository adapter (SQLAlchemy/asyncpg) and Spectora importer
  behind `TemplateRepository`/`TemplateImporter`; API routes that thread `UserContext.owner_id`.
- Migration tooling preference: plain SQL files applied via `psql` (default, portable) vs. a
  tool like Alembic/`supabase db push` — plain SQL chosen for now.