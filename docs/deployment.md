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
- `CORS_ORIGINS` (comma-separated frontend origins)
- `APP_ENV=production`
- `GEMINI_API_KEY` only if/when AI is used

## Frontend — Vercel

- Framework preset: Vite. Build output: `dist/`.
- Env vars (public only): `VITE_API_BASE_URL` → the Render service URL.
- Never put secrets in frontend env vars — the browser ships them to clients.

## Database — Supabase

- Supabase is the **managed PostgreSQL hosting layer**, not the application backend.
- Apply migrations from `database/migrations/` via `psql` against the Supabase connection
  string (see `database/migrations/README.md`) or `supabase db push` if the CLI is used.
- Full step-by-step (SQL Editor / psql / CLI, verification queries, live checks):
  see `docs/supabase-deployment.md`.

## CI/CD pipeline

CI (`.github/workflows/ci.yml`) runs on push/PR for `main` and feature branches:

1. Backend: ruff lint → pytest (including tests that verify layering/imports).
2. Frontend: `npm ci` → `tsc --noEmit` → `vite build`.
3. Optionally, migrations are applied to a disposable PostgreSQL service container.

Deploy steps are triggered in the Vercel/Render consoles (git-connected), keeping CI lean.