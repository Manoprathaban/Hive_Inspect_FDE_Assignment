# Deployment

| Service   | Host      | How it ships                                 |
| --------- | --------- | -------------------------------------------- |
| Frontend  | Vercel    | Import the `frontend/` dir; build = `npm run build` |
| Backend   | Render    | Deploy from `backend/` (Dockerfile or native Python) |
| Database  | Supabase  | PostgreSQL migrations from `database/migrations/` |

## Backend — Render

`backend/Dockerfile` builds a Python 3.13 image that runs `uvicorn app.main:app`.

Render blueprint (`render.yaml`) is intentionally **not** added yet — it can be generated
later from the Render dashboard. Required env vars when it is:

- `DATABASE_URL` (Supabase PostgreSQL connection string)
- `CORS_ORIGINS` (comma-separated frontend origins). The built-in default covers local
  development only — `http://localhost:5173` (Vite dev), `http://localhost:4173`
  (`npm run preview`, i.e. the production build) and `http://localhost:3000`. In a
  deployment it must contain the exact frontend origin, e.g.
  `CORS_ORIGINS=https://<app>.vercel.app`, or every browser call is blocked by CORS.
- `APP_ENV=production`
- `GEMINI_API_KEY` only if/when AI is used

## Frontend — Vercel

- Framework preset: Vite. Build output: `dist/`.
- Env vars (public only): `VITE_API_BASE_URL` → the Render service URL.
- Never put secrets in frontend env vars — the browser ships them to clients.
- Real Supabase sign-in additionally needs `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_ANON_KEY` (the public anon key). Without them the app runs on the
  development session, which the production backend rejects — see `docs/FRONTEND_DESIGN.md`
  §7 and §32.

## Database — Supabase

- Supabase is the **managed PostgreSQL hosting layer**, not the application backend.
- Apply migrations from `database/migrations/` via `psql` against the Supabase connection
  string (see `database/migrations/README.md`) or `supabase db push` if the CLI is used.
- Full step-by-step (SQL Editor / psql / CLI, verification queries, live checks):
  see `docs/supabase-deployment.md`.

## CI/CD pipeline

CI (`.github/workflows/ci.yml`) runs on push to `main` and on pull requests, restricted to
`backend/**`, `frontend/**`, `database/**`, and the workflow file itself.

Three independent jobs mirror the local quality gates:

1. Backend: `pip install -r requirements.txt` → `ruff check .` → `ruff format --check .` → `pytest`
   (including tests that verify layering/imports).
2. Frontend: `npm ci` → `npm run lint` → `npm run typecheck` → `npm test` → `npm run build`.
3. Database: migrations applied in order to a disposable PostgreSQL 17 service container →
   `ruff check .` → `pytest` (schema/RLS/ownership tests on a fresh database).

pip and npm dependency caches are keyed on the lock/requirements files. No job receives
secrets; deployment credentials stay in the Render/Vercel secret stores.

Deploy steps are triggered in the Vercel/Render consoles (git-connected), keeping CI lean.