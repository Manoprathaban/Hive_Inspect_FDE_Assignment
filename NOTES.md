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

## 2026-09-29 — Production JWT authentication

- Implemented real Supabase Auth JWT validation in `app/adapters/authentication/supabase.py`
  (`SupabaseAuthProvider`), finally replacing the fails-closed stub. It verifies the access
  token with HS256 against `SUPABASE_JWT_SECRET`, requires `exp` (enforced) and `sub` (a
  UUID → `UserContext.user_id`), and — critically — requires **both** `aud` and `role` to
  be `authenticated`. Supabase signs its `anon`/`service_role` API keys with the same JWT
  secret, so without the role/aud check a leaked public key would mint a valid bearer
  credential; the role check rejects those keys outright. `iss` is verified too when
  `SUPABASE_URL` is configured (expected value `<url>/auth/v1`). Fails closed (raises) if
  the secret is missing.
- Protocol: `AuthenticationProvider.get_current_user(token: str)` — the API layer strips
  the `Bearer` scheme and hands every provider the raw token. `DevAuthProvider` ignores the
  value; `SupabaseAuthProvider` attests it. The auth dependency's §14 mapping is unchanged:
  missing header → `401 AUTHENTICATION_REQUIRED`; any provider rejection →
  `401 INVALID_TOKEN` (never distinguishable, identical `WWW-Authenticate: Bearer`).
- Wiring: `app/api/dependencies/auth.py` now picks the provider by `Settings.app_env` —
  `production` → `SupabaseAuthProvider` (built from `SUPABASE_JWT_SECRET`/`SUPABASE_URL`),
  anything else → `DevAuthProvider`. Tests were untouched because the offline suite runs in
  `development`; the production path is covered by a new dependency-override test file
  (`tests/test_supabase_auth.py`).
- Token-envelope detail kept: the header stays **required** in development too
  (missing → 401), only its value is ignored — matching the existing API tests and the
  §6 table, and contradicting an earlier "optional" phrase in §4.Development that is now
  corrected in `docs/API-CONTRACTS.md`.
- Tests: `tests/test_supabase_auth.py` mints HS256 tokens with a test secret (unit tests
  for acceptance, bad signature, expired, wrong role/audience/issuer, malformed, non-UUID
  `sub`, missing claims) plus API-wiring tests that inject the production provider and
  assert `200` on a valid token and `401`/`401` on missing/invalid credentials. Provider
  unit coverage 100%; `supabase.py` 29/29.
- Docs: `DATABASE_DESIGN.md` §14 (protocol + adapter contract), §18 (API-key JWT confusion),
  §19 (item removed); `API-CONTRACTS.md` §4 (verification rules) and §6 (header table);
  `architecture.md` (auth boundary in "Established now"); `NOTES.md`; `backend/.env.example`
  (`SUPABASE_JWT_SECRET`, `SUPABASE_URL`); PyJWT pinned in `requirements.txt`.

## 2026-09-29 — Frontend (Phase 4)

- Implemented the app from `docs/FRONTEND_DESIGN.md` on `feature/frontend`: auth
  (`/login`), template list, import, template view with inline editing, duplication, and
  the import-issues panel. React 19 + TypeScript + Vite, React Router, and
  `@supabase/supabase-js` for the browser session.
- **Server state vs UI state (§11)**: a dependency-free query cache in
  `src/lib/query.tsx` (`useQuery`/`useMutation`/`useCacheUpdater`/`useQueryStore`,
  backed by `useSyncExternalStore`) holds all API data and is cleared wholesale on logout
  so no data crosses users. Editing draft text, dialog visibility, and the import phase
  machine are component state. No server data is mirrored into component state.
- **No optimistic writes (§13)**: a PATCH resolves from the `204` and the confirmed value
  is applied to the cache *and* refetched, so "Saved" is never claimed before the backend
  confirmed. The inline editor keeps the user's draft plus the error on failure, and
  disables double-submit while saving.
- **Errors (§20)**: one HTTP boundary (`src/lib/apiClient.ts`) turns the contract
  envelope into a typed `ApiError`; `describeError` maps each code to actionable copy,
  and any `401` clears the session so the router guard returns to `/login`. Responses are
  runtime-validated against the contract shapes, so a contract mismatch surfaces as an
  error instead of rendering `undefined`.
- **Auth (§7)**: `AuthProvider` restores a Supabase session, subscribes to auth changes,
  and keeps the bearer token in sync. With no `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY`
  it falls back to a deterministic dev session, which the backend `DevAuthProvider`
  accepts — so the whole flow runs offline. No secret ever enters a frontend env var.
- **Import (§12)**: the dialog checks the file client-side (extension + 10 MiB, mirroring
  the contract limits), uploads via `XMLHttpRequest` because `fetch` reports no upload
  progress, and shows percentage → "Importing…" → navigation. Upload timeout is 600s on
  purpose: a cold run of the committed export on the deployed database exceeds a minute
  and the server keeps going, so a 60s client timeout would abandon a successful import.
- Tests: 7 files / 56 tests (error normalization and contract guards, query cache
  semantics, HTTP client request shapes and error mapping, import validation, the login
  reducer, and the inline-editor/import-issues components). `npm run lint`,
  `npm run typecheck`, `npm test`, `npm run build` all pass.
- Live check against the deployed Supabase backend through the dev server: import of
  `sample-data/sheet1.xml` (13 sections / 69 items / 392 comments / 520 options, 4 issues),
  read-back, the three PATCHes with persistence re-read, import-issues, a duplicate with
  independent ids carrying the edited values, the list endpoint, `401` without a bearer
  token, and CORS preflight/`Access-Control-Allow-Origin` for the dev origin. Test data
  was deleted afterwards.
- Vitest runs on the `threads` pool: the default `forks` pool could not start workers in
  this environment. Two files carry targeted `eslint-disable` comments with reasons
  (`react/only-export-components` for provider + hooks modules, and
  `react/set-state-in-effect` for the Supabase session restore, which is a real external
  sync).

## 2026-09-29 — Phase 5 integration (live stack)

- Added `backend/tests/test_live_api_integration.py`: the acceptance flows of
  `docs/FRONTEND_DESIGN.md` §28 driven over HTTP against a **running** server and real
  PostgreSQL, the way the browser drives it. It is opt-in and skips itself without
  `LIVE_API_BASE_URL`, so the offline run and CI are unaffected:
  `LIVE_API_BASE_URL=http://127.0.0.1:8020 uv run pytest tests/test_live_api_integration.py`.
- What it covers and why the existing suites could not: the serialized response shapes the
  type guards in `frontend/src/lib/types.ts` accept; the real multipart import of
  `sample-data/sheet1.xml` (13/69/392/520 plus 4 issues); all three PATCHes returning an
  empty `204` and **persisting** across a refetch with `display_order` and comment options
  intact; duplicate independence (fresh ids at every level, provenance, no copied issues,
  and an edit on the copy leaving the original untouched); the error envelope for a
  rejected upload (`415 INVALID_FILE`, nothing persisted); the import-issues endpoint
  answering "what was skipped and why"; an indistinguishable `404`; and `401` without a
  bearer token.
- The canonical export is imported once per module (a cold import against the deployed
  database is slow) and deleted again through PostgreSQL afterwards, because the API
  contract has no delete route. Cleanup verifies the rows are gone and fails the suite
  otherwise, so a repeatable run leaves the shared dev database untouched (confirmed: 0
  templates before and after).
- **Integration gap found and fixed:** the browser could not talk to a production build of
  the frontend. `npm run preview` serves on port **4173**, which was not in the allowed
  origins, so every API call from the built app would have failed CORS. `CORS_ORIGINS` now
  defaults to `http://localhost:5173,http://localhost:4173,http://localhost:3000` in
  `settings.py` and `.env.example`, and the live suite asserts preflight plus a real
  cross-origin `GET` for each of those origins (including the `authorization` and
  `content-type` request headers the app actually sends). `docs/deployment.md` now states
  that a deployment must set the exact frontend origin.
- **CHECK BLOCKED — real Supabase Auth end-to-end.** The frontend's production path
  (signup → session JWT → API) cannot be exercised here: the project's **public anon key**
  (`VITE_SUPABASE_ANON_KEY`) is not in this environment, and `backend/.env` only holds the
  JWT secret and URL. It needs the anon key plus one Auth user, then
  `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` in `frontend/.env.local` and the backend
  running with `APP_ENV=production` (`SupabaseAuthProvider`). Everything up to the token
  handoff is verified: the dev session, the `401` path, and the production provider's unit
  and API-wiring tests from Phase 3.

## 2026-09-29 — Phase 6 (CI/CD + deployment validation)

- **CI now mirrors the local gates.** `docs/deployment.md` previously claimed a frontend
  pipeline of "typecheck + build" and treated migrations as optional. The workflow now runs
  the real gate set on every push to `main` and every pull request that touches
  `backend/**`, `frontend/**`, `database/**`, or the workflow file:
  - backend: `ruff check .` → `ruff format --check .` → `pytest`
  - frontend: `npm run lint` → `npm run typecheck` → `npm test` → `npm run build`
  - database: migrations applied in order to a disposable PostgreSQL 17 service, then the
    schema/RLS/ownership suite against that fresh database
- **`ruff format` is now enforced, so the repo was formatted.** The backend had 44 files
  that predated the formatter (a pre-existing, non-CI-enforced caveat) and 14 that already
  matched. They are now all formatted, `ruff format --check .` is clean, and the workflow
  will fail on drift. No behaviour changed: `144` tests collected, `134` passed / `10`
  live-skipped, and app coverage is unchanged at `97%` (`1036` statements, `26` missed).
- **npm and pip caches** are keyed on `frontend/package-lock.json` and
  `backend/requirements.txt`, and no job is given secrets; deployment credentials stay in
  the Render/Vercel secret stores.
- **CHECK BLOCKED — no hosted CI run.** The workflow executes on `main` pushes and on pull
  requests. This branch was pushed without opening a PR (not requested), so GitHub Actions
  has not executed the new jobs. Every command they run was executed locally instead and
  passes; a PR is the remaining trigger.
- **CHECK BLOCKED — deployment wiring cannot be exercised from here.** Verifying the
  Vercel/Render wiring needs the actual deployed hostnames: `CORS_ORIGINS` must equal the
  exact frontend origin, and the frontend's `VITE_API_BASE_URL` must point at the deployed
  API. `docs/deployment.md` states both requirements; the values themselves are deployment
  secrets/environment settings, not repository content.

## 2026-09-29 — Phase 7 (final assignment verification)

Audit of the build against `assignment.md`, item by item. This is the pass that found the
one thing that would have cost real marks, so it is worth recording what was checked.

- **The live app had nothing to open on.** The assignment requires the deployed app to
  "open on an imported template" and the database was empty (0 templates) after Phase 5
  cleaned up after itself. Added `backend/scripts/seed_sample_template.py`, which imports
  `sample-data/sheet1.xml` through the *real* `SpectoraXlsxImporter` and persists it through
  the *real* `PostgresTemplateRepository` — deliberately not hand-written SQL, so what the
  reviewer sees is exactly what an upload produces, and the seed cannot drift from the
  importer. Re-runnable (exits 0 if the owner already has templates, `--force` to override)
  so it is safe on every deploy, and `--dry-run` parses without writing.
- **Seeded and verified through the public API, not just the database.** The live stack now
  returns the full tree: 13 sections / 69 items / 392 comments / 520 options and 4 import
  issues, matching the canonical figures from Phases 2 and 5 exactly. Confirmed
  `GET /api/templates`, `GET /api/templates/{id}`, and `GET .../import-issues` serve the
  seeded data, then cleaned the test copy back out.
- **Re-verified the two baseline behaviours the assignment calls out by name** against the
  seeded template: an edit persists, and a duplicate is genuinely independent (distinct
  template *and* section ids; editing the copy left the original untouched). One scare
  during this check was my own test script, not the code: it indexed `[0]` into a list
  ordered by `updated_at DESC`, so after editing the copy it read the copy back and looked
  like the original had been mutated. The database showed distinct section ids and
  untouched original content — copy independence was never broken. Restored the section
  name afterwards, so the seeded template is in its as-imported state.
- **Proved the importer works beyond the one committed template.** The brief says "We may
  try another export in the same HTML-text format", and until now every importer test ran
  against the same InterNACHI file, so the honest limitation was "verified on one export
  only". Added `sample-data/commercial-rental.xml` — a synthetic export in the identical
  SpreadsheetML format, but structurally unlike the canonical one: 12 columns instead of
  42 (every optional column the importer models is absent), a different template, and one
  extra column the importer has no home for. It imports correctly, which is the evidence
  that the mapping is header-driven rather than tuned to InterNACHI. It also carries four
  dirty values that each surface as an issue instead of being silently coerced. Six new
  `test_second_export_*` tests pin all of it.
- **Confirmed the reviewer's artifacts are present and correct:** the real Spectora
  InterNACHI Residential export is committed at `sample-data/sheet1.xml` (338 KB) with
  provenance in `sample-data/README.md`; `assignment.md` is correctly *not* tracked
  (`.gitignore`); no `__pycache__`/`.pytest_cache`/`.ruff_cache` is tracked; no `.env` is
  tracked.

## 2026-09-30 — Sign-in, logout and deployment fixes

- **Real sign-in had never worked against the live database.** Newer Supabase projects sign
  their tokens with RS256 (older ones ES256) rather than the HS256 the backend expected, so
  every genuine sign-in was rejected. The auth provider now handles both, reading the
  project's public keys, and `SUPABASE_JWT_SECRET` is only required for the old symmetric
  setup. This also surfaced a missing dependency — verifying an RS256/ES256 signature needs
  `cryptography`, which was not installed, so that path would have crashed on first use.
- **Logout existed but nothing called it.** The only way out of a session was for an API call
  to fail. Added a proper log-out button to the app shell, so it is available on every screen
  rather than being tied to one page.
- **Fixed the deployed frontend 404ing on refresh.** A hard refresh on a template page returned
  "not found" because the static host had no route fallback for client-side paths. Added one.
- CI is now running on GitHub's runners on every push and every pull request, not just locally.

## 2026-09-30 — Made opening a template much faster

This is the improvement I chose to spend the extra time on. An inspector opens a template they
have tuned for four years and then works in it for an hour, so the cost of that hour is what
this removes.

- **The page was redoing all its work on every change.** Opening the issues panel, dismissing a
  message, or saving an edit caused the viewer to rebuild all 392 comments from scratch,
  because the components were handed freshly created callbacks each time and so never
  recognised anything as unchanged. Fixed by keeping those callbacks stable. On the real
  template the first load went from 723 ms to a 4 ms re-render when you interact with
  something unrelated, and there is now a test that fails if that regresses.
- **The backend asked the database five questions in a row** when loading a template, each one
  waiting on the answer before it could ask the next, even though none of them actually
  depended on each other. They now run at the same time. I diffed the responses before and
  after against four real templates to confirm the output is byte-for-byte identical.
- Widened the connection pool, since parallel reads need more than one spare connection.
- No API change, and the frontend still refetches after a save rather than trusting its own
  local copy.
- The numbers above are measured locally. The remote database is too inconsistent between runs
  to quote an honest end-to-end figure, so I did not.

## 2026-09-30 — Made the tenant separation real

- **The row-level security in the database was not actually protecting anything.** I had
  written the policies, but PostgreSQL does not apply them to the user that owns the tables —
  and that is how the backend was connecting. So all seven policies were sitting there doing
  nothing, and nothing failed to warn me, because the application code was separately checking
  ownership on every query. A single mistake in that code would have exposed every customer's
  templates with no error anywhere. I found this while verifying the live database rather than
  by reading the code, which is the only reason it came out at all.
- **The fix was to give the backend its own restricted database role** that does not own
  anything, so the policies apply to it, and to tell the database who the current user is
  inside the request's own transaction. Because that is transaction-scoped, a reused
  connection cannot carry one customer's identity into the next request — there is a test for
  exactly that failure.
- Checked against the live database: the owner sees their 14 templates, another identity sees
  none, and trying to insert a row claiming someone else's ownership is refused by the
  database itself. Nothing in the live data was changed by this check.
- One thing worth knowing if you deploy this elsewhere: the new role comes from a migration,
  so it has to be applied before running the updated backend. It is already applied on the live
  project.

## 2026-09-30 — Fixed development sign-in sharing one account

- **Found while checking the work above: signing in with different credentials showed the same
  templates every time.** The development sign-in ignored whatever you typed and always
  returned the same seeded user, and the frontend only ever sent a fixed placeholder, so there
  was no way to enter a different account at all.
- **Now each set of credentials gets its own workspace.** The account is derived from the
  credential, so it is stable across restarts and two accounts can never collide. `demo@hive.test`
  still opens the seeded template; any other email starts empty. A real Supabase token is now
  also respected rather than thrown away, and a new account gets its user row created on first
  request so saving works straight away.
- Confirmed on the live database: the demo account sees the seeded template, two fresh accounts
  see nothing, and one account trying to open another's template gets a plain "not found" —
  the same response as a template that does not exist.
- No database change needed for this one.

## 2026-09-30 — The live app

Deployed and checked against the real hosts rather than localhost:

| | |
| --- | --- |
| App | https://hive-inspect-fde-assignment.vercel.app |
| API | https://hive-inspect-fde-assignment.onrender.com |

- **The seeded template had gone missing from the live database**, so the live app opened on an
  empty screen — the one thing a reviewer is meant to be able to see immediately. Re-imported it
  through the same code path an upload uses and confirmed through the public API that it reads
  13 sections / 69 items / 392 comments / 520 options, matching the original export exactly.
- Confirmed on the deployed backend: health check passes, the browser's cross-origin checks
  pass from the Vercel address, a request without a session is rejected, and one account
  cannot read another's template.
- **Signing in:** use `demo@hive.test` to open the seeded template. Any other email can be
  registered normally and gets its own empty workspace, so it is easy to show the separation
  between two accounts.
- One leftover test template belonging to another account is still in the database; harmless,
  and I left it rather than deleting data.

## Supported input and known limitations

- **Supported input:** the Spectora "Export HTML Text" (SpreadsheetML worksheet) format
  that `sample-data/sheet1.xml` uses, i.e. a single worksheet whose row 1 is a header
  describing each column. The importer is column-driven, not template-driven: it maps by
  header name, so a different Spectora template in the same format works without code
  changes. Evidenced twice — the canonical InterNACHI export, and
  `sample-data/commercial-rental.xml`, a deliberately different 12-column export that omits
  every optional column the importer models. No *real* second vendor export was available to
  test with, so the second fixture is synthetic.
- **Preserved:** section/item/comment text, the full hierarchy, explicit ordering, comment
  options, and per-row source references.
- **Deliberate limits:** the worksheet format only (not the plain-text or XLSX exports);
  a fixed set of known Spectora columns; cells that cannot be represented in the schema are
  **surfaced as import issues, never dropped silently** — that is what the 4 issues on the
  canonical file are (2 warnings for unrepresentable data, 2 info for empty source columns).
- **Not built, on purpose:** actual inspection reports, scheduling, payments, and any
  homeowner-facing surface (explicitly out of scope in the assignment), plus template
  `delete` through the API (not in the contract; the repository method exists for tests and
  seeding only).

## What I cut and why

- **AI in the import path.** The importer is deterministic. For this customer, a template
  they tuned for four years is worth more if every row either lands or raises a visible
  issue; a model that silently rewords or drops content is the worse failure. The
  `TemplateImporter` protocol keeps the seam open if that judgement is wrong.
- **A full template editor.** Editing section names, item names, and comment text covers the
  baseline "Edit" requirement. Rich structural editing (reordering, adding items) was cut as
  a non-technical inspector's real need being better served by making import trustworthy
  first.
- **Playwright/browser E2E.** Cut deliberately: the same flows are covered by 79 frontend
  tests plus the live HTTP/CORS suite in `backend/tests/test_live_api_integration.py`, and
  browser automation was a better use of the remaining time than more polish.
- **Template delete through the API.** The API contract has no delete route, so deleting a
  template someone uploaded is not possible from the app today. That is a real gap for the
  customer, and leaving it out was a scope decision rather than something I forgot.

## Credits

- **Spectora** — the InterNACHI Residential template export committed in `sample-data/` is
  their sample material, used here as importer input.
- **React + Vite frontend scaffold** — the React/TypeScript frontend was bootstrapped with
  Lovable-assisted scaffolding; the API client, state layer, auth flow, template list/view/
  edit/duplicate screens, import-issue UI, and their tests are project work.
- Everything else (FastAPI backend, SQL migrations, Supabase schema, importer, repository,
  CI) was written for this assignment. No third-party application code was vendored.

## Time spent

Roughly two focused days for the baseline, matching the assignment's estimate: schema and
migrations, backend domain and application, REST API, frontend, live-stack integration, and CI.
The biggest single cost there was import fidelity — the importer itself and the checks behind
the 13/69/392/520 figures.

The 2026-09-30 work was extra, and about the same size again: getting real sign-in working,
logout, the deployment fixes, then the template-load speed work, the database-level tenant
separation, and the development sign-in fix.

Of everything, the two security items are what I would keep first if there were no deadline.
Both were found by checking the live deployment rather than by reading the code, and both had
been invisible from inside the test suite precisely *because* the application layer was doing
the right thing. That is the part I would most want to talk through in the walkthrough.

## Where to look

| | |
|---|---|
| Live app | https://hive-inspect-fde-assignment.vercel.app/login |
| Walkthrough video | https://drive.google.com/file/d/1pHVY5zA0TZTlQdJlGg8K6hMUIdJKkY78/view?usp=sharing |

### Signing in to the already imported template

The seeded template already exists, so this account opens straight onto it:

```
email:    jaohnlahord@gmail.com
password: Mano@2001
```

It lands on the InterNACHI Residential template I imported from the committed Spectora
export: 13 sections, 69 items, 392 comments, and its 4 import issues. There is nothing to
upload first — the point of seeding it was so the app opens with something to explore.

### Seeing a separate account of your own

Sign up with any other email address instead. Sign-up sends a verification mail; once you
confirm it, the new account has its own empty tenant and cannot see the seeded template or
any other account's data. That is the fastest way to see the separation working: log out of
the seeded account, sign in as yourself, and the template list is empty.

The seeded account and a self-registered account are both real accounts in the same database
with real authentication — the only difference is that one happens to own a template.

