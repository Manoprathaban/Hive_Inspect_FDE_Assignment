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
- **Schema is not decided yet.** The real template schema (sections/items/comments) is
  intentionally deferred. `database/migrations/` documents conventions only.

## Tech stack (locked)

- Frontend: React + TypeScript (Lovable-assisted), independent from the backend.
- Backend: Python, FastAPI, Pydantic, Uvicorn; SQLAlchemy + asyncpg for PostgreSQL later.
- DB: PostgreSQL on Supabase (managed hosting layer only — not the app backend).
- AI: Gemini only where it adds real value, always behind a replaceable service boundary.
- Ship: Vercel (frontend), Render (backend), Supabase (DB).

## Open questions

- Exact template data model (sections/items/comments hierarchy) — next phase.
- Whether authentication is in scope and against which provider.
- Migration tooling preference: plain SQL files applied via `psql` (default, portable) vs.
  a tool like Alembic/`supabase db push`.