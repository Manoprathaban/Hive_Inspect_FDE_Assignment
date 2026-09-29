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
- Backend: Python, FastAPI, Pydantic, Uvicorn; SQLAlchemy (async) + asyncpg wired for
  PostgreSQL in the repository-adapter phase.
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

## 2026-09-29 — Template read API

- Implemented `GET /api/templates`, `GET /api/templates/{id}`, and
  `GET /api/templates/{id}/import-issues` against §9.1/§9.2/§11: summaries newest-first by
  `updated_at`, one full hierarchy (§13.2, never exposing issues/`owner_id`), and persisted
  diagnostics newest-first. No pagination/filtering (§19).
- Ownership stays the data it always was: a missing **or** foreign template is the same
  `404 TEMPLATE_NOT_FOUND` (§20). The import-issues route first resolves the template with
  the owner-scoped `get`, since the repository boundary returns `[]` for missing/foreign.
- Also aligned the §14 note: the envelope's `401` responses now set
  `WWW-Authenticate: Bearer` (this applies to every endpoint, import included).
- All three read endpoints are now on the same `TemplateRepository` adapter the import
  phase introduced; no repository or contract changes were needed for reads.
- Schemathesis on this phase: added the RFC 9110 `Allow` header to `405` responses
  app-wide (was flagged on every operation), clearing those findings. Two documented
  findings remain, both accepted: (1) `ignored_auth` — the dev auth provider accepts any
  token by design (offline-only; the production provider validates tokens), and (2) the
  known `415 INVALID_FILE` on a schema-compliant `file` part whose filename is not a
  recognized container — the contract-required §18 response.

## 2026-09-29 — Template editor API

- Implemented the write/edit surface (§9.4/§10/§17) in the in-memory-backed repository:
  `POST /api/templates/{id}/duplicate` and the three PATCHes
  (`.../sections/{id}`, `.../items/{id}`, `.../comments/{id}`).
- Duplicate (§17): ownership-scoped deep copy with brand-new ids for the template and
  every descendant, own timestamps, `copied_from_id` provenance, **no** import issues
  copied, default `"<source name> (Copy)"` or an optional trimmed 1–200 `{"name"}` body
  (`null`/absent → default name); `201` + the new `Template` + `Location` header.
- PATCHes (§10): exactly one required field per body (`{"name"}` sections/items trimmed
  1–200; `{"content"}` comments verbatim, empty clears), `204` empty. Bodies reject extra
  fields (`extra="forbid"`) → `422 VALIDATION_ERROR`.
- §20 error mapping: missing/foreign template → `404 TEMPLATE_NOT_FOUND`; once the owned
  template is verified, an unresolvable child id → child-specific `404 SECTION_NOT_FOUND` /
  `ITEM_NOT_FOUND` / `COMMENT_NOT_FOUND`. Added four domain exceptions
  (`TemplateNotFoundError`, `SectionNotFoundError`, `ItemNotFoundError`,
  `CommentNotFoundError`) and mapped them in the routes.
- §21: edits are single-row updates — the template's `updated_at` is **not** bumped
  (repository and API tests both pin this).
- Repository: `update_section_name`/`update_item_name`/`update_comment_content`/
  `duplicate` now implemented behind a private `_owned` helper (missing/foreign raise
  `TemplateNotFoundError`); `delete` stays `NotImplementedError` (not exposed by the
  contract, fails loudly).
- Tests: repository unit tests + a new `tests/test_template_edit_api.py` suite (duplicate
  independence/Location/naming/404s/422s, PATCH persistence/trimming/404s, 401s, and an
  import→duplicate→edit end-to-end against `sample-data/sheet1.xml`).
- Coverage now 98% overall; `app/adapters/repositories/in_memory.py` at 99% (the single
  miss is the unexposed `delete`).
- Schemathesis on this phase surfaced two routing/schema quirks, both fixed properly:
  (1) `GET /import` was being shadowed by `GET /{template_id}` (`import` isn't a UUID,
  so it answered 422 instead of 405); a schema-hidden `import_guard_router` (no auth
  dependency, registered ahead of the main router) now returns `405` + `Allow: POST` for
  any non-`POST` method on the import resource while `/{template_id}` keeps its documented
  `422` on non-UUID ids. (2) The empty-name 422s looked like rejections of
  schema-compliant data; `RenameRequest.name`/`DuplicateRequest.name` now declare
  `min_length=1, max_length=200` so OpenAPI encodes §12's bound. Only the two accepted
  residuals remain (`ignored_auth`, and 415 `INVALID_FILE` on the unrecognized `file`
  part).

## 2026-09-29 — Postgres repository adapter

- Implemented the PostgreSQL `TemplateRepository` adapter as a single self-contained module,
  `backend/app/adapters/repositories/postgres.py` (SQLAlchemy 2.0 async + asyncpg engine).
  No ORM mapping: every operation is a raw SQLAlchemy Core `text()` statement following the
  parameterized query patterns in `docs/DATABASE_DESIGN.md` §20, and a connection is opened
  lazily per operation so building the app never connects to Postgres.
- Implements the full `TemplateRepository` protocol: `save` (one transaction persisting the
  aggregate with fresh ids down the tree), `get`, `list_for_user` (newest `updated_at`
  first, `id` tiebreak), `list_import_issues` (`created_at DESC, id DESC`), the three
  `update_*` single-row edits, `duplicate` (one transaction, new ids everywhere,
  `copied_from_id` provenance, own timestamps, no issues, default `<source> (Copy)` name),
  and an owner-scoped `delete`.
- Ownership is enforced inside every statement — child rows by an `EXISTS` that walks the
  parent chain to the template owner — so missing **or** foreign templates and unresolvable
  child ids produce the exact same 404 mapping as the in-memory adapter
  (`TemplateNotFoundError`, then child-specific `SectionNotFoundError`/
  `ItemNotFoundError`/`CommentNotFoundError`); edits never touch `templates`, so
  `updated_at` stays stable (§21). RLS (`0002`) remains defense in depth, never the app's
  ownership mechanism.
- Wiring: `app/api/dependencies/providers.py` binds one process-wide
  `PostgresTemplateRepository(get_async_engine())`; the engine comes from
  `app/infrastructure/database` (asyncpg URL from `Settings.database_url`, local-dev
  default) and is shared via `lru_cache`. SQLAlchemy constructs the engine without
  connecting, and `database_url` has a default, so offline imports and the in-memory
  overrides in the test suite are unaffected.
- Tests: new `backend/tests/test_postgres_repository.py` — a live-PostgreSQL suite that
  mirrors the `database/tests` harness: each test creates a throwaway database, applies the
  versioned migrations in order, and drops it on teardown. It skips itself when no server
  is reachable (`TEST_DATABASE_ADMIN_URL`, defaulting to the local dev credentials) so the
  offline run and CI's backend job stay green. It covers the save→get round trip
  (including an end-to-end pass of the canonical Spectora export), cross-user isolation,
  list/issue ordering, single-row edit semantics and child-specific 404s, transactional
  duplicate independence, and cascade delete.
- Docs updated: `docs/architecture.md` (adapter boundary), `docs/API-CONTRACTS.md`
  (§9/§25 now "CONTRACT AS IMPLEMENTED," Postgres-backed), `docs/DATABASE_DESIGN.md`
  (§19 item removed; validation-status banner and §18 now reflect the live-Postgres
  harness and migration runs).

## Open questions

- Next phase: wire real token validation into the production authentication provider
  (the dev stub fails closed today; see `docs/BACKEND_DESIGN.md` /
  `docs/API-CONTRACTS.md` §24), or begin frontend integration
  (`docs/FRONTEND_DESIGN.md`).
- Migration tooling preference: plain SQL files applied via `psql` (default, portable) vs.
  a tool like Alembic/`supabase db push` — plain SQL chosen for now.
- Deliberately out of scope until its phase: exposing template `delete` through the API
  (the contract does not define a delete route; the repository's owner-scoped `delete`
  exists for the database boundary and is covered by the live suite).