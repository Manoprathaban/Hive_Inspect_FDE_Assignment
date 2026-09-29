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
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell)
source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs. Copy `backend/.env.example` to
`backend/.env` to override defaults.

Run the checks used in CI:

```bash
ruff check .
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
`http://localhost:5173` and `http://localhost:3000` — already allow the dev server).
No secrets live in frontend env vars.

With no `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` set, the app uses the deterministic
development session (any credentials; requests carry the dev token the backend's
`DevAuthProvider` accepts). Set both to sign in against real Supabase Auth.

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

## Deployment

- Frontend → Vercel
- Backend  → Render (see `backend/Dockerfile` and `docs/deployment.md`)
- Database → Supabase PostgreSQL

## Phase

Phases 1–4 are implemented: database schema/migrations, backend domain + application,
the REST API from `docs/API-CONTRACTS.md`, and the React frontend from
`docs/FRONTEND_DESIGN.md`. Phase 5 (integration) and later phases are tracked in
`NOTES.md`.
