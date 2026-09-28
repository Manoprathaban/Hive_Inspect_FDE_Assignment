# frontend

React + TypeScript frontend for Hive Inspect Template Importer. Generated and assisted by
Lovable; this folder stays **independent** from the backend and only talks to it over HTTP.

## Local development

```bash
npm install
npm run dev
```

Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to the backend URL if it is not
`http://localhost:8000`.

## Commands

| Command          | Purpose                        |
| ---------------- | ------------------------------ |
| `npm run dev`    | Dev server with HMR            |
| `npm run build`  | Type-check + production build  |
| `npm run typecheck` | TypeScript type-check only  |
| `npm run lint`   | Oxlint                         |
| `npm run preview`| Preview the production build   |

## Notes

- Environment variables are **public only**; no secrets live here.
- Vercel deploy: framework preset Vite, build output `dist/`.