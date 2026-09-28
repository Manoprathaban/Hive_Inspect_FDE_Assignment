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

## 2026-09-29 — Template import API

- Implemented `POST /api/templates/import` against `docs/API-CONTRACTS.md` §9.3/§18:
  contract routes mounted under the `/api` base path (`/health` stays at the root);
  `multipart/form-data` `file` upload with a 10 MiB cap, extension+content container
  validation (`413 FILE_TOO_LARGE` / `415 INVALID_FILE`), importer-driven structure
  validation (`422 INVALID_XLSX` with the reason in `details`), atomic save of the
  aggregate + its issues, `201 ImportResult` (template + issues newest-first) and
  `Location: /api/templates/{id}`.
- Added the §14 error envelope (single handler wiring for `ApiError`,
  `RequestValidationError`, malformed-multipart 400 → `422 VALIDATION_ERROR`, and the
  never-leaky `500 INTERNAL_ERROR`) plus the bearer-auth dependency
  (`AUTHENTICATION_REQUIRED`/`INVALID_TOKEN`) using the dev auth provider.
- Applied §27 consistency-issue 1: optional ids on every nested domain resource plus
  `created_at`/`updated_at`/`copied_from_id` on `Template` (schema already had the columns).
- Added `InMemoryTemplateRepository` (owner-scoped, assigns real ids/timestamps;
  `update_*`/`duplicate`/`delete` raise `NotImplementedError` until their phases).
  Added `max_upload_bytes` to settings and `python-multipart` to `requirements.txt`.
- Schemathesis validated the OpenAPI schema against the running app; one residual finding
  is the documented false positive for an empty `file` part (415 on a non-container, which
  is the contract-mandated response — see `docs/API-CONTRACTS.md` §18).

## Open questions

- Next phase: `GET /api/templates`, `GET /api/templates/{id}`, the three PATCH endpoints,
  duplicate, and `GET /api/templates/{id}/import-issues`, backed by the Postgres repository
  adapter (SQLAlchemy/asyncpg) implementing the same owner-scoped protocol.
- Migration tooling preference: plain SQL files applied via `psql` (default, portable) vs. a
  tool like Alembic/`supabase db push` — plain SQL chosen for now.