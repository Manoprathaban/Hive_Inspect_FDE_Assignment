# Deployment

| Service   | Host      | How it ships                                 |
| --------- | --------- | -------------------------------------------- |
| Frontend  | Vercel    | Import the `frontend/` dir; build = `npm run build` |
| Backend   | Render    | Deploy from `backend/` (Dockerfile or native Python) |
| Database  | Supabase  | PostgreSQL migrations from `database/migrations/` |

## Backend — Render

`backend/Dockerfile` builds a Python 3.13 image that runs `uvicorn app.main:app`. It now
honors Render's injected `PORT` (falling back to `8000` for local Docker).

The Render blueprint is committed at the repo root (`render.yaml`): a `docker` Web Service
named `hive-inspect-api` with `rootDir: backend`, `healthCheckPath: /health`, and
`APP_ENV=production`.

### Deploy steps (one-time)

1. Push/merge the backend as `main`.
2. Render dashboard → **New +** → **Blueprint** → select this GitHub repo.
3. Render creates the `hive-inspect-api` Web Service from `render.yaml`.
4. In the service's **Environment** tab set the values marked `sync: false`:
   - `DATABASE_URL` — Supabase session-pooler asyncpg URL (see `docs/supabase-deployment.md`),
     e.g. `postgresql+asyncpg://postgres.<ref>@aws-0-<region>.pooler.supabase.com:5432/postgres?ssl=require`
   - `SUPABASE_URL` — `https://<project-ref>.supabase.co`
   - `SUPABASE_JWT_SECRET` — project JWT secret (Supabase dashboard → Settings → API →
     JWT Settings)
   - `CORS_ORIGINS` — comma-separated allowed frontend origins (Vercel URL once shipped)
5. Save; Render redeploys. Verify `GET <service-url>/health` returns `200`.
6. Optional PR Plugs/instance: on the free plan the service auto-sleeps when idle.

`GEMINI_API_KEY` is only needed if/when AI features are scoped.

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