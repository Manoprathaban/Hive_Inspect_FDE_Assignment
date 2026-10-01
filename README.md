# Hive Inspect Template Importer

Import Spectora inspection templates into Hive Inspect through a clean, replaceable importer
architecture. Hiring through Technical Assignment Round.

## Technology Decisions

| Layer      | Tech                                        |
| ---------- | ------------------------------------------- |
| Frontend   | React + TypeScript (Lovable-assisted)       |
| Backend    | Python, FastAPI, Pydantic, Uvicorn          |
| Database   | PostgreSQL hosted on Supabase               |
| AI         | Optional, behind a replaceable boundary     |
| Frontend deployment | Vercel                              |
| Backend deployment  | Render                                |
| Database deployment | Supabase PostgreSQL                   |

## Repository Layout

```
frontend/       React + TypeScript app (independent of backend)
backend/        FastAPI modular monolith
database/       Migrations and seed data for PostgreSQL (Supabase)
sample-data/    Real-world sample inputs for importers
docs/           Architecture, database, and deployment notes
.github/        CI/CD workflows
```

See `docs/architecture.md` for the layered architecture and dependency direction.

## Backend

The backend is a modular monolith. Application and domain code never depend directly on
FastAPI request objects, the XLSX parser, Supabase/PostgreSQL details, or any AI SDK —
those dependencies stay at the edges (adapters/infrastructure) behind protocols.

Protocols already established:

- `TemplateImporter` — import a template source into a domain model
- `TemplateRepository` — persistence boundary for templates

### Local development

```bash
cd backend
uv sync                                              # or: pip install -r requirements.txt
uv run uvicorn app.main:app --reload                 # or: uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs. Copy `backend/.env.example` to
`backend/.env` to override defaults.

Run the checks used in CI:

```bash
ruff check .
ruff format --check .
pytest
```

## Frontend

React + TypeScript SPA (Vite). It talks to the backend over HTTP only — no direct
Supabase/PostgreSQL access from the browser.

```bash
cd frontend
npm install
npm run dev
```

Copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE_URL` to the
backend URL (default `http://localhost:8000`, so the backend's default CORS origins —
`http://localhost:5173`, `http://localhost:4173`, `http://localhost:3000` — already allow
the dev server and a production-build preview). No secrets live in frontend env vars.

The backend chooses its authentication provider from `APP_ENV`: `production` verifies Supabase
JWTs (HS256/RS256/ES256) and fails closed, anything else uses the development provider. The two
must agree — a development backend accepts a per-credential session that a production backend
would reject.

With no `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` set, the app signs in against the
development backend, which turns the email you type into a workspace: `demo@hive.test` (or
the "Continue as demo user" button) reaches the seeded templates, and any other email starts
an empty one. The password is never sent. Set both variables to sign in against real Supabase
Auth instead.

Quality gates (same commands CI runs):

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

## Database

Migrations and seeds live in `database/`. Migrations are plain SQL so they execute
consistently on local PostgreSQL, Supabase, and CI. See `database/migrations/README.md`.

Tenant isolation is enforced by Postgres row-level security, not only by the application. The
API connects as a non-owner role (`hive_app`) and sets the request identity inside the
transaction, so a pooled connection cannot leak one tenant's identity into the next request.
Apply the migrations **in order** — `0003_rls_enforcement.sql` creates the role the API expects.
Setting `DB_APP_ROLE=` (empty) disables this and is only correct for a plain PostgreSQL instance
with no `auth` schema.

## Deployment

- Frontend → Vercel
- Backend  → Render (see `backend/Dockerfile` and `docs/deployment.md`)
- Database → Supabase PostgreSQL

## Live app

| | URL |
| --- | --- |
| Frontend | https://hive-inspect-fde-assignment.vercel.app |
| Backend API | https://hive-inspect-fde-assignment.onrender.com |
| Database | Supabase PostgreSQL |

It opens on the seeded Spectora InterNACHI template. Sign in with `demo@hive.test` to reach it,
or sign up with any email to get your own empty tenant (each account is isolated by Postgres RLS).
See `NOTES.md` for access details and known limitations.

## Phase

Phases 1-6 are implemented: database schema/migrations, backend domain + application, the
REST API from `docs/API-CONTRACTS.md`, the React frontend from `docs/FRONTEND_DESIGN.md`,
live-stack integration against the deployed Supabase database, and CI mirroring the local
quality gates. Tenant isolation is enforced in the database (`database/migrations/0003_rls_enforcement.sql`),
not only in the application layer. See `NOTES.md` for the phase-by-phase record, the cut list,
and known limitations.

## Seeding a template

The deployed app is seeded with the committed Spectora export so it opens on something to
explore. The seed runs the real importer and the real repository (no hand-written SQL), so
what a reviewer sees is exactly what an upload produces:

```bash
cd backend
uv run python -m scripts.seed_sample_template            # no-op if templates exist
uv run python -m scripts.seed_sample_template --dry-run  # parse and report, write nothing
```

Flags: `--owner-id UUID` (defaults to the dev auth user), `--force` to add another copy.
