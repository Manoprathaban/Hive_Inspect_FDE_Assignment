# Architecture

Hive Inspect Template Importer is a **modular monolith** with explicit boundaries. No
microservices. The structure itself enforces the dependency direction.

## Dependency direction

```
API/Routes  →  Application  →  Protocols / Domain  →  Adapters  →  Infrastructure
      │            │                  │                    │              │
   FastAPI      use cases          contracts         concrete impls   FastAPI-hosted
   (HTTP)       (orchestration)    (what we need)    (how we do it)   edges (DB,
                                                                      config, logging)
```

**Application and domain code must never import:**

- FastAPI request/response objects (`Request`, `UploadFile`, ...)
- the XLSX parsing library
- the Supabase SDK or asyncpg/SQLAlchemy dialect specifics
- the Gemini (AI) SDK

Those live at the edges (adapters + infrastructure). Inverting them keeps noisy, volatile
dependencies outside the business logic.

## Layers (`backend/app`)

| Layer            | Path                    | Responsibility                                    |
| ---------------- | ----------------------- | ------------------------------------------------- |
| Presentation/API | `api/`                  | HTTP routes, middleware, request dependencies     |
| Application      | `application/`          | Use cases + application services (orchestration)  |
| Domain           | `domain/`               | Entities, domain models, exceptions               |
| Protocols        | `protocols/`            | `Protocol` contracts for replaceable capabilities |
| Adapters         | `adapters/`             | Concrete implementations of the protocols         |
| Infrastructure   | `infrastructure/`       | Database wiring, config, logging                  |
| Entry point      | `main.py`               | Creates the FastAPI app, wires the API router     |

## Protocol-first boundaries

Boundaries are `typing.Protocol` classes. The application depends on the protocol; any
adapter can satisfy it.

### Established now

- **`TemplateImporter`** (`protocols/importers/`)
  Converts a template source (e.g. Spectora worksheet XLSX/XML) into a domain
  `TemplateImport`. The application use case calls the protocol, so the concrete importer
  is swappable:

  ```
  TemplateImporter (protocol)
      ├── Spectora XLSX importer      (future)
      ├── Other brand importer        (future)
      └── MockTemplateImporter        (now — test/mock)
  ```

- **`TemplateRepository`** (`protocols/repositories/`)
  Persistence boundary for templates. A PostgreSQL adapter
  (`adapters/repositories/postgres.py`, SQLAlchemy async + asyncpg) and an in-memory
  adapter (`adapters/repositories/in_memory.py`, tests/offline) both satisfy it.

- **`AuthenticationProvider`** (`protocols/authentication.py`)
  Resolves a bearer token into a domain `UserContext` (`user_id` → `templates.owner_id`).
  The API layer picks the concrete provider by environment: dev stub in `development`,
  Supabase JWT validation in `production`.

  ```
  AuthenticationProvider (protocol)
      ├── DevAuthProvider           (development — deterministic user)
      └── SupabaseAuthProvider      (production — HS256 JWT verification)
  ```

### Reserved for later (no code yet)

- **`ContentProcessor`** — transforms parsed content (auto-generation, dedupe, formatting).
- **`AIService`** — any Gemini/LLM capability, only where it adds real value. Kept behind a
  protocol so `GeminiAIService` is replaceable by a stub or another provider.
- **`FileStorage`** — raw file persistence (original uploads, generated XLSX).

## Package layout (py.typed)

Every package ships an `__init__.py` with a docstring naming its contract so the
boundaries stay legible even before features exist. `py.typed` marks the project as
type-annotated.

## Testing

- Unit tests exercise use cases against mock adapters (no network, no DB).
- The `/health` route is integration-tested with `TestClient`.
- CI runs `ruff check .` and `pytest` against the backend; tsc + vite build for frontend.