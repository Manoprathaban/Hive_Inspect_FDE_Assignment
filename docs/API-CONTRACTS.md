# API Contracts

Hive Inspect Template Importer — REST HTTP contract between the **frontend**, the
**FastAPI backend**, and the **application/use-case layer**.

This document freezes the API surface **before** backend implementation. The backend must
follow this contract; the frontend must not rely on behavior that is not documented here.

---

## 1. Purpose

The API supports exactly the workflow the assignment requires:

- import a Spectora HTML-text spreadsheet export (XLSX)
- preserve hierarchy, ordering, and comment/content text
- make unsupported or skipped content visible
- edit section names, item names, and comment text
- persist edits in a real backend (PostgreSQL)
- retrieve templates
- duplicate a template and edit the copy independently
- authenticated ownership and user-level authorization

Explicitly **out of scope** — must NOT be exposed by this API: inspections, reports,
scheduling, payments, homeowner portals, customers, properties, analytics, notifications,
generic CRUD for child tables, AI features, and administrative dashboards.

The single source of truth for the data model behind this contract is
`docs/DATABASE_DESIGN.md` together with `database/migrations/0001_create_template_schema.sql`
and `0002_rls_policies.sql`. Every resource, field name, and ordering rule here comes from
those documents.

---

## 2. API Principles

1. **REST over HTTP.** Resources addressable by URL; verbs express the operation.
2. **Business operations, not table CRUD.** The API exposes template-scoped operations.
   Child tables (sections/items/comments/options) are never exposed as top-level resources
   and never have standalone create/delete/list endpoints.
3. **Ownership is never client-supplied.** The acting user's identity comes from the
   authenticated `UserContext`; path IDs identify *which* resource, not *whose*.
4. **Deterministic ordering.** Every list and hierarchy response is explicitly ordered.
   Clients never receive rows in insertion order and must not depend on it.
5. **One error format** for every endpoint (see §14).
6. **Minimal surface.** No pagination/filter/search machinery unless the data size
   justifies it (§19). No idempotency-key infrastructure (§21).
7. **No undocumented behavior.** Anything the frontend receives is defined here.

---

## 3. Base URL / Versioning

- **Base path:** `/api`. All contract endpoints live under this prefix.
- **Versioning:** none. This is a two-day assignment with one client; `/api/v1/...` adds
  cost without a requirement. If a breaking change becomes unavoidable after the API is
  live, the change lands behind `/api/v2` (§26) — never a silent mutation of `/api`.
- Existing convention: the health probe lives at `GET /health` (outside `/api`). It is an
  operational probe, not part of this contract.
- Host is environment-specific (local `http://localhost:8000`, Render for the deployed
  backend per `docs/deployment.md`). Relative paths are used throughout this document.

---

## 4. Authentication

### Production (Supabase Auth)

HTTP header on every endpoint except `/health`:

```
Authorization: Bearer <Supabase JWT>
```

Backend flow:

```
JWT (Bearer header)
   ↓
AuthenticationProvider (authentication boundary)
   ↓
UserContext { user_id, provider, email? }
   ↓
Application use case / repository (authorization scoping)
```

- **Identity model:** the authenticated user's `user_id` maps 1:1 to
  `templates.owner_id`. `auth.users.id` == `public.users.id` in production (mirror
  trigger in migration `0001`).
- **Missing token:** `401 AUTHENTICATION_REQUIRED`.
- **Invalid token:** `401 INVALID_TOKEN`. **Expired token:** `401 INVALID_TOKEN` — the API
  does not distinguish invalid from expired responses (no extra information leak, and the
  `WWW-Authenticate: Bearer` challenge is identical).
- 401 responses carry `WWW-Authenticate: Bearer` unless otherwise noted.

### Development

When the backend runs in `APP_ENV=development`, the existing `DevAuthProvider` resolves
every request to a single deterministic user
(`00000000-0000-0000-0000-000000000001`, seeded by `database/seed/dev_auth.sql`). In
development the `Authorization` header is optional and, if present, its value is ignored —
the caller is always the dev user.

> The development path must never be reachable in production. The production path must
> never accept an identity supplied by the client.

---

## 5. Authorization

- The **client never supplies ownership**: no `owner_id`, `user_id`, or `created_by`
  field exists in any request body or query string. Attempts to do so are ignored or
  rejected as `VALIDATION_ERROR`.
- The backend derives the acting user from the `UserContext` and scopes every repository
  operation to it: every `TemplateRepository` method takes the acting `owner_id` and the
  adapter/RLS enforce it (`docs/DATABASE_DESIGN.md` §5–§6).
- For nested operations the backend verifies the full chain:
  - `PATCH .../sections/{id}` → template owned by `user_id` **and** section belongs to
    that template.
  - `PATCH .../items/{id}` → template owned **and** item→section→template chain resolves.
  - `PATCH .../comments/{id}` → template owned **and** comment→item→section→template chain
    resolves.
- Cross-user access does **not** surface a `403`. It surfaces the same generic `404` a
  missing resource would (see §20). `403 FORBIDDEN` is reserved in the error contract for
  an authenticated, ownership-verified operation the user is not permitted to perform —
  no such endpoint exists today.

---

## 6. Common Headers

| Header | Required | Value | Notes |
| --- | --- | --- | --- |
| `Authorization` | Yes (except `/health`, dev) | `Bearer <JWT>` | Production: Supabase Auth JWT. Development: optional/ignored (§4). |
| `Content-Type` | For requests with a body | `application/json` | Except `POST /api/templates/import` which uses `multipart/form-data`. |
| `Accept` | No | `application/json` | All responses are JSON. |

Timestamps: RFC 3339 / ISO 8601 in UTC, e.g. `2026-09-28T12:34:56Z`.
IDs: UUID strings (RFC 4122, lowercase canonical form).

---

## 7. Resource Model

Business resources exposed by the API (the JSON shapes are the *contract*; they are not
database rows):

| Resource | API visibility | Notes |
| --- | --- | --- |
| `Template` | Full resource | List, retrieve, import, duplicate. |
| `Section` | Template-scoped | Editable via `PATCH .../sections/{id}`. Only appears nested in a template. |
| `Item` | Template-scoped | Editable via `PATCH .../items/{id}`. Only appears nested. |
| `Comment` | Template-scoped | Editable via `PATCH .../comments/{id}`. Only appears nested. |
| `CommentOption` | Read-only | Returned nested in comments (multiple choice + unit type). Never edited. |
| `ImportIssue` | Read-only per template | Diagnostic visibility for skipped/unsupported/missing content. |

No top-level resources for sections, items, comments, options, or issues.

---

## 8. Endpoint Summary

Master contract table. Every endpoint in the API appears here. All paths are relative to
`/api`. All endpoints (except `/health`) require authentication.

| # | Method | Path | Auth | Purpose | Request | Response | Success | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET` | `/templates` | Yes | List the caller's templates (summaries) | — (no query params) | `TemplateSummary[]` (§13.1) | `200` | `401` `500` |
| 2 | `GET` | `/templates/{template_id}` | Yes | Fetch one template with full ordered hierarchy | — | `Template` (§13.2) | `200` | `401` `404` `500` |
| 3 | `POST` | `/templates/import` | Yes | Import a Spectora XLSX export | `multipart/form-data`, file field `file` | `ImportResult` (§13.4) | `201` | `401` `413` `415` `422` `500` |
| 4 | `POST` | `/templates/{template_id}/duplicate` | Yes | Create an independent copy | JSON body, optional (`name`) | `Template` (the copy) (§13.2) | `201` | `401` `404` `422` `500` |
| 5 | `PATCH` | `/templates/{template_id}/sections/{section_id}` | Yes | Rename a section | JSON `{"name": str}` | — (empty body) | `204` | `401` `404` `422` `500` |
| 6 | `PATCH` | `/templates/{template_id}/items/{item_id}` | Yes | Rename an item | JSON `{"name": str}` | — (empty body) | `204` | `401` `404` `422` `500` |
| 7 | `PATCH` | `/templates/{template_id}/comments/{comment_id}` | Yes | Replace a comment's content text | JSON `{"content": str}` | — (empty body) | `204` | `401` `404` `422` `500` |
| 8 | `GET` | `/templates/{template_id}/import-issues` | Yes | List import issues for a template | — | `ImportIssue[]` (§13.5) | `200` | `401` `404` `500` |

Deleted by design: `DELETE /templates/{id}` is **not** exposed. The assignment workflow
(import → work → copy) never requires deletion, and exposing it would add destroy risk
with no customer value in scope; `TemplateRepository.delete` remains available to tests and
internal cleanup. Adding a delete endpoint later is a deliberate contract change (§26).

---

## 9. Template APIs

### 9.1 List Templates — `GET /api/templates`

Returns the caller's templates as lightweight summaries, **newest first** by
`updated_at` (matching `TemplateRepository.list_for_user`, ordered by `updated_at`).

- Authentication: yes (§4).
- Query parameters: none. No pagination (§19); no sorting/filtering parameters
  (§19).
- Empty result: `200` with `[]`.
- Errors: `401`, `500`.

### 9.2 Get Template — `GET /api/templates/{template_id}`

Returns one template with its **complete** hierarchy, ordered deterministically:

```
Template → Sections → Items → Comments → CommentOptions
```

- Ordering rules in §16.
- The response **never** includes `issues` (fetched via §11) and **never** exposes
  `owner_id` or FK columns.
- A template the caller does not own, or that does not exist, returns `404
  TEMPLATE_NOT_FOUND` — indistinguishable responses (§20).
- Errors: `401`, `404` (`TEMPLATE_NOT_FOUND`), `500`.

### 9.3 Import Template — `POST /api/templates/import`

- Content type: `multipart/form-data`.
- Single file field named `file`. The field is required.
- Accepted file: a Spectora HTML-text spreadsheet export (XLSX document; the committed
  sample `sample-data/sheet1.xml` is the inner worksheet of that format family). Full
  validation rules in §18.
- Response: option **B** — `ImportResult` = created template + import issues. Justified:
  the assignment requires skipped/unsupported content to be visible immediately after
  import, issues are persisted so they can also be re-read, and the frontend needs a
  single round trip to render both the template and the "import had issues" banner.
- On success: `201 Created`, body `ImportResult` (§13.4).
- `source` on the created template is set by the importer (`spectora`); `source_filename`
  preserves the uploaded filename; the template `name` is derived by the importer from the
  filename (base name without extension) unless the source carries an explicit title
  (importer-owned decision, documented in the importer phase).
- Errors: `401`, `413` (`FILE_TOO_LARGE`), `415` (`INVALID_FILE`), `422`
  (`INVALID_XLSX`, `VALIDATION_ERROR`), `500`.

### 9.4 Duplicate Template — `POST /api/templates/{template_id}/duplicate`

Creates an **independent, fully new** copy owned by the caller. Full duplication contract
in §17.

- Request body: optional JSON `{"name": str}`. When omitted, the copy is named
  `"<source name> (Copy)"`.
- Response: `201 Created`, body = the **new** template (§13.2) so the frontend can navigate
  to it directly. The new `id` is what distinguishes the copy; `copied_from_id` records
  provenance.
- Authorized only when the source template is owned by the caller; otherwise `404
  TEMPLATE_NOT_FOUND`.
- Errors: `401`, `404`, `422`, `500`.

### 9.5 Delete Template

Not exposed — see §8.

---

## 10. Editing APIs

All three PATCH endpoints share the same rules:

- Request body: JSON with exactly **one required field** (targeted single-field update;
  there is no generic partial-update machinery).
- Success: `204 No Content`, empty body. The client refreshes the affected template via
  `GET /api/templates/{template_id}` when it needs fresh data. Rationale: the repository
  boundary returns no body on edits, and returning the whole aggregate on every keystroke
  would be redundant with `GET`.
- Field semantics:
  - `name` (sections, items): **required**, non-null, trimmed length 1–200.
    `null` → `422 VALIDATION_ERROR`; empty string `""` → `422 VALIDATION_ERROR`.
  - `content` (comments): **required**, non-null. Empty string is **allowed** and clears
    the comment text (column is `NOT NULL DEFAULT ''`). `null` → `422 VALIDATION_ERROR`.
- The comment field is named **`content`** — it is the actual schema/domain field
  (`comments.content`), not `text`.
- Authorization: template ownership + child-chain verification (§5). Any unresolved id in
  the chain returns `404` with the generic or child-specific code per §20.
- All errors: `401`, `404`, `422`, `500`.

### 10.1 Rename Section — `PATCH /api/templates/{template_id}/sections/{section_id}`

Request: `{"name": "Exterior"}`. Repoints `sections.name` for a section owned by the
caller's template.

### 10.2 Rename Item — `PATCH /api/templates/{template_id}/items/{item_id}`

Request: `{"name": "Roof covering"}`. Repoints `items.name`.

### 10.3 Edit Comment — `PATCH /api/templates/{template_id}/comments/{comment_id}`

Request: `{"content": "New text"}`. Replaces `comments.content` for the comment instance.
`content` may contain markup only in the sense that the stored text is preserved verbatim
(see §18, rich content handling); the API performs no HTML sanitization — the column is
plain text and any markup is passed through as-is.

---

## 11. Import Issue API

### GET /api/templates/{template_id}/import-issues

Lists **persisted** diagnostics recorded for an import, newest first
(`created_at DESC`, then `id DESC` as tiebreaker).

- Issue types (enum `issue_type`): `SOURCE_DATA_MISSING`, `UNSUPPORTED_CONTENT`,
  `INVALID_SOURCE_DATA`.
- Severities (enum `issue_severity`): `info`, `warning`, `error`.
- No filtering parameters — the full list is returned (§19).
- The response makes skipped/unsupported content visible to the user; it is never a
  generic "import failed" swallow.
- Errors: `401`, `404` (`TEMPLATE_NOT_FOUND`), `500`.

---

## 12. Request Schemas

Exact JSON bodies (all fields required unless marked optional).

### 12.1 Rename section / item

```json
{ "name": "string" }
```

- `name`: `string`, **required**. Trimmed length 1–200. Non-null.

### 12.2 Edit comment

```json
{ "content": "string" }
```

- `content`: `string`, **required**. Any length ≥ 0 (empty clears). Non-null.

### 12.3 Duplicate template (optional body)

```json
{ "name": "string" }
```

- `name`: `string`, **optional**. Trimmed length 1–200. When present, it overrides the
  default copy naming. When absent, `"<source name> (Copy)"`. Non-null if present.

### 12.4 Import file (multipart)

- Part name: `file`.
- Content type of the part: an XLSX/SpreadsheetML export; validated per §18 (MIME is not
  trusted).
- Maximum size: 10 MiB (constant, documented in backend configuration).
- Exactly one file. Missing part → `422 VALIDATION_ERROR`.

---

## 13. Response Schemas

Contracts below mirror the domain/schema shapes. Response JSON uses `camelCase` **snake**
field names matching the database exactly: `source_filename`, `copied_from_id`,
`comment_type`, `answer_type`, `display_order`, etc.

### 13.1 TemplateSummary (list item)

| Field | Type | Req | Meaning |
| --- | --- | --- | --- |
| `id` | uuid string | yes | Template id (`templates.id`) |
| `name` | string | yes | `templates.name` |
| `source` | string | yes | Importer brand/format (`templates.source`) |
| `source_filename` | string \| null | yes | `templates.source_filename` |
| `created_at` | datetime | yes | `templates.created_at` (RFC 3339 UTC) |
| `updated_at` | datetime | yes | `templates.updated_at` (RFC 3339 UTC) |

```json
[
  {
    "id": "2f1c...-uuid",
    "name": "InterNACHI Residential",
    "source": "spectora",
    "source_filename": "interNACHI-template.xlsx",
    "created_at": "2026-09-28T12:34:56Z",
    "updated_at": "2026-09-28T12:34:56Z"
  }
]
```

### 13.2 Template (full hierarchy)

| Field | Type | Req | Meaning |
| --- | --- | --- | --- |
| `id` | uuid string | yes | `templates.id` |
| `name` | string | yes | `templates.name` |
| `source` | string | yes | `templates.source` |
| `source_filename` | string \| null | yes | `templates.source_filename` |
| `copied_from_id` | uuid string \| null | yes | Provenance only (`templates.copied_from_id`) |
| `created_at` | datetime | yes | `templates.created_at` |
| `updated_at` | datetime | yes | `templates.updated_at` |
| `sections` | Section[] | yes | Ordered (§16) |

**Section** (nested):

| `id` | uuid string | yes | `sections.id` |
| `name` | string | yes | `sections.name` |
| `display_order` | int ≥ 0 | yes | Zero-based, unique within template |
| `items` | Item[] | yes | Ordered (§16) |

**Item** (nested):

| `id` | uuid string | yes | `items.id` |
| `name` | string | yes | `items.name` |
| `display_order` | int ≥ 0 | yes | Zero-based, unique within section |
| `comments` | Comment[] | yes | Ordered (§16) |

**Comment** (nested):

| Field | Type | Req | Meaning |
| --- | --- | --- | --- |
| `id` | uuid string | yes | `comments.id` |
| `name` | string | yes | `comments.name` |
| `content` | string | yes | `comments.content` (may be `""`, may carry markup) |
| `comment_type` | enum | yes | `info` \| `limit` \| `defect` |
| `category` | int \| null | yes | `comments.category`: `-1` Low, `0` Med, `1` High, or `null` |
| `answer_type` | enum | yes | `boolean` \| `checkbox` \| `date` \| `number` \| `range` \| `text` |
| `display_order` | int ≥ 0 | yes | Zero-based (non-unique by design; §16) |
| `recommendation` | string \| null | yes | `comments.recommendation` |
| `default_value` | string \| null | yes | `comments.default_value` |
| `default_value_2` | string \| null | yes | `comments.default_value_2` |
| `default_unit_type` | string \| null | yes | `comments.default_unit_type` |
| `estimate_min` | number \| null | yes | `comments.estimate_min` |
| `estimate_max` | number \| null | yes | `comments.estimate_max` |
| `source_row` | int \| null | yes | Original spreadsheet row (provenance) |
| `options` | CommentOption[] | yes | Ordered (§16) |

**CommentOption** (nested):

| `option_type` | enum | yes | `multiple_choice` \| `unit_type` |
| `value` | string | yes | `comment_options.value` |
| `display_order` | int ≥ 0 | yes | Zero-based |

```json
{
  "id": "uuid",
  "name": "InterNACHI Residential",
  "source": "spectora",
  "source_filename": "interNACHI-template.xlsx",
  "copied_from_id": null,
  "created_at": "2026-09-28T12:34:56Z",
  "updated_at": "2026-09-28T12:34:56Z",
  "sections": [
    {
      "id": "uuid",
      "name": "Exterior",
      "display_order": 0,
      "items": [
        {
          "id": "uuid",
          "name": "Roof covering",
          "display_order": 0,
          "comments": [
            {
              "id": "uuid",
              "name": "General roof covering",
              "content": "Inspect the roof covering...",
              "comment_type": "defect",
              "category": null,
              "answer_type": "boolean",
              "display_order": 0,
              "recommendation": null,
              "default_value": null,
              "default_value_2": null,
              "default_unit_type": null,
              "estimate_min": null,
              "estimate_max": null,
              "source_row": 30,
              "options": []
            }
          ]
        }
      ]
    }
  ]
}
```

**Not exposed:** `owner_id`, and all FK columns (`template_id`, `section_id`, `item_id`,
`comment_id`). They are internal structure; nesting already conveys the relationships.

### 13.3 Created headers

`POST /templates/import` and `POST /templates/{id}/duplicate` set
`Location: /api/templates/{new_or_existing_template_id}` on `201`. (For import it is the
new template; for duplicate it is the new copy's id.)

### 13.4 ImportResult

`{ "template": Template (§13.2), "issues": ImportIssue[] (§13.5) }`

- `template`: the freshly persisted template, full hierarchy.
- `issues`: every diagnostic recorded for this import, newest first.

The frontend renders the template and surfaces any non-empty `issues` immediately.

### 13.5 ImportIssue

| Field | Type | Req | Meaning |
| --- | --- | --- | --- |
| `id` | uuid string | yes | `import_issues.id` |
| `issue_type` | enum | yes | `SOURCE_DATA_MISSING` \| `UNSUPPORTED_CONTENT` \| `INVALID_SOURCE_DATA` |
| `severity` | enum | yes | `info` \| `warning` \| `error` |
| `message` | string | yes | Human-readable description (`import_issues.message`) |
| `source_row` | int \| null | yes | `import_issues.source_row` |
| `source_field` | string \| null | yes | `import_issues.source_field` |
| `raw_value` | string \| null | yes | `import_issues.raw_value` |

```json
{
  "template": { "…": "…" },
  "issues": [
    {
      "id": "uuid",
      "issue_type": "UNSUPPORTED_CONTENT",
      "severity": "warning",
      "message": "Source column 'Locked' contained data that cannot be represented.",
      "source_row": 45,
      "source_field": "Locked",
      "raw_value": "true"
    }
  ]
}
```

---

## 14. Error Contract

**One envelope for every error across all endpoints:**

```json
{
  "error": {
    "code": "TEMPLATE_NOT_FOUND",
    "message": "Template was not found.",
    "details": null
  }
}
```

- `code`: stable string, defined here. The frontend switches on this, not on message text.
- `message`: human-readable, may vary.
- `details`: `null`, or structural payload (e.g. `{ "name": ["must be 1-200 characters"] }`
  for `VALIDATION_ERROR`; `{ "reason": "..." }` for file errors).

### Error codes

| Code | Status | Meaning |
| --- | --- | --- |
| `AUTHENTICATION_REQUIRED` | 401 | Missing `Authorization` header (production) |
| `INVALID_TOKEN` | 401 | Token invalid or expired (indistinguishable by design) |
| `FORBIDDEN` | 403 | Reserved today (see §5; no endpoint produces it yet) |
| `VALIDATION_ERROR` | 422 | Request body failed schema/validation rules (§12) |
| `TEMPLATE_NOT_FOUND` | 404 | Template missing **or not owned** (generic, non-leaking) |
| `SECTION_NOT_FOUND` | 404 | Template verified owned; section id not under it |
| `ITEM_NOT_FOUND` | 404 | Template verified owned; item id not under it |
| `COMMENT_NOT_FOUND` | 404 | Template verified owned; comment id not under it |
| `INVALID_FILE` | 415 | Media/ext not a recognized Spectora export (MIME untrusted) |
| `INVALID_XLSX` | 422 | Recognized format, unreadable/corrupt/invalid structure |
| `FILE_TOO_LARGE` | 413 | Upload exceeds the 10 MiB limit |
| `DATABASE_CONFLICT` | 409 | Unavoidable unique/constraint conflict (rare; see §21) |
| `INTERNAL_ERROR` | 500 | Unexpected failure; never leaks stack traces or internals |

> `IMPORT_FAILED` was evaluated and intentionally **not** added: a fatal, understandable
> failure is a specific, client-actionable code (`INVALID_FILE` / `INVALID_XLSX`), and an
> unknown failure is `INTERNAL_ERROR`. A generic "import failed" bucket would give the
> frontend nothing to branch on. Non-fatal import problems are **not errors** — they are
> persisted `import_issues` and succeed with `201` (§18).

401 responses to a token problem also set `WWW-Authenticate: Bearer`.

---

## 15. HTTP Status Codes

Codes used by this API and when:

| Code | Used by | When |
| --- | --- | --- |
| `200 OK` | All GETs | Successful retrieval |
| `201 Created` | `POST /templates/import`, `POST /templates/{id}/duplicate` | Resource created |
| `204 No Content` | PATCH edits (§10) | Mutation succeeded, empty body |
| `400 Bad Request` | — | **Not used** by this API. Malformed requests surface as `415`/`413`/`422` instead of a catch-all 400 (keeps errors predictable). |
| `401 Unauthorized` | Every endpoint | Missing/invalid/expired token (production) |
| `403 Forbidden` | — | Reserved; not produced by any endpoint today (§5) |
| `404 Not Found` | ID-bearing endpoints | Missing resource **or cross-user access** (generic) |
| `409 Conflict` | Any write (rare) | Unavoidable uniqueness conflict (§21) |
| `413 Payload Too Large` | `POST /templates/import` | File > 10 MiB |
| `415 Unsupported Media Type` | `POST /templates/import` | Not a recognized export (§18) |
| `422 Unprocessable Entity` | Validation-bearing endpoints | Schema/validation failure, corrupt XLSX |
| `500 Internal Server Error` | Any | `INTERNAL_ERROR`, never leaky |

---

## 16. Ordering Contract

Ordering is deterministic and explicit; insertion order is never used.

- **Sections:** `ORDER BY display_order` (`sections` unique per template, so plain order).
- **Items:** `ORDER BY display_order` (unique per section).
- **Comments:** `ORDER BY display_order, id` — `comments.display_order` is **non-unique**
  by design (source may repeat values), so the unique `id` is the deterministic
  tiebreaker. This matches the appendix query pattern in `DATABASE_DESIGN.md` §20.
- **CommentOptions:** first by `option_type`, then `display_order`
  (`GROUP BY comment_id, option_type, display_order`) — the schema unique constraint is
  `(comment_id, option_type, display_order)`.
- **ImportIssues:** `ORDER BY created_at DESC, id DESC`.
- **Template list:** `ORDER BY updated_at DESC` (per `list_for_user`).

Every nested array in a `Template` response MUST be returned in the above orders.

---

## 17. Duplication Contract

`POST /api/templates/{template_id}/duplicate` performs a transactional, ownership-scoped
deep copy (the `TemplateRepository.duplicate` semantics of `DATABASE_DESIGN.md` §12):

- **New ids:** the copy gets a new `templates.id` and brand-new ids for every section,
  item, comment, and option. Child FKs are remapped to the copy's new ids. No mutable
  child row is ever shared.
- **Independence:** because nothing is shared, editing the copy can never mutate the
  original (structurally impossible, plus RLS `WITH CHECK`; §20).
- **Copied content:** name behavior per §12.3; all content fields, `display_order`, and
  `owner_id` are copied.
- **Provenance:** the copy's `copied_from_id` = source template id. It is provenance
  only; deleting the source sets it `NULL` and never breaks copies
  (FK `ON DELETE SET NULL`).
- **Import issues:** **not** copied — they describe the original's specific import.
- **Timestamps:** `created_at`/`updated_at` on the copy are its own.
- **Transaction:** either the entire copy succeeds or none of it exists (single
  transaction). A partial copy is excluded by contract.
- **Response:** `201` + full new template (§13.2); `Location` points at the new template.
- Errors: `401`, `404` (`TEMPLATE_NOT_FOUND` — includes "source not owned"),
  `422` (invalid `name`), `500`.

---

## 18. Import Contract

### Input

- A Spectora HTML-text spreadsheet export. The committed sample
  `sample-data/sheet1.xml` (SpreadsheetML worksheet) is the canonical fixture and is in
  the same format family as the XLSX container the assignment describes.
- The importer backend: validate → parse → reconstruct hierarchy → map fields (§16 of
  `DATABASE_DESIGN.md`) → persist atomically → return `ImportResult`.

### Validation — fatal vs non-fatal

| Situation | Result |
| --- | --- |
| Part `file` missing | `422 VALIDATION_ERROR` |
| Upload exceeds 10 MiB | `413 FILE_TOO_LARGE` |
| Extension/type not any recognized export container | `415 INVALID_FILE` (extension AND content/MIME checked; MIME alone is never trusted) |
| Recognized format but corrupt/unreadable | `422 INVALID_XLSX` |
| Expected sheet missing (e.g. `Sheet1` worksheet absent) | `422 INVALID_XLSX` |
| Required structured columns missing | `422 INVALID_XLSX` (fatal — structure cannot be reconstructed) |
| Optional/misc columns empty | `SOURCE_DATA_MISSING` issue (`info`) — recorded, not fatal |
| Optional columns populated but not modelable | `UNSUPPORTED_CONTENT` issue (`warning`) with `source_field` + `raw_value` (§16 rule against silent loss) |
| Invalid value in a mapped field (e.g. unknown `Comment Type`) | `INVALID_SOURCE_DATA` issue, row still imported with a safe fallback where possible; if it makes the row unusable, `422 INVALID_XLSX` with the row context |

Fatal errors return the error envelope; non-fatal conditions become persisted
`import_issues` and the import succeeds.

### Rich content

- All text is preserved verbatim after XML-entity decoding; no HTML sanitization is
  performed by the API or storage (the column is free-form `TEXT`). Render-side rules are
  deliberately out of scope at this phase (documented in `DATABASE_DESIGN.md` §16).
- The template is **never** stored as one opaque blob; it is split into
  section/item/comment/option rows.

### Atomicity and cleanup

- The import succeeds or fails entirely (single transaction); a recorded template and its
  issues appear together.
- Uploaded bytes are read fully into memory (10 MiB cap) and the temporary upload file is
  removed by the server after the request; uploaded files are never persisted and never
  exposed publicly.

---

## 19. Pagination / Filtering

- **No pagination** anywhere in v1.
  - Template lists: a single inspector owns a handful of templates; the summary list is
    returned complete. If this grows, cursor pagination on `updated_at` is the deferred
    design.
  - A template's hierarchy is small (the committed sample: 13 sections, 61 items, 392
    comments) and the assignment needs the full structure for editing; it is always
    returned whole.
  - Import issues: returned complete, newest first.
- **No sorting/filtering parameters** — the only explicit orders are those in §16. No
  generic `?sort=&filter=&search=&include=&expand=` system.

---

## 20. Security / IDOR Protection

Cross-user access is structurally impossible through the API design:

| Attempt | Observable result |
| --- | --- |
| `GET /templates/{id}` on another user's template | `404 TEMPLATE_NOT_FOUND` |
| `PATCH .../sections/{id}` on another user's section | `404 TEMPLATE_NOT_FOUND` |
| `PATCH .../items/{id}` on another user's item | `404 TEMPLATE_NOT_FOUND` |
| `PATCH .../comments/{id}` on another user's comment | `404 TEMPLATE_NOT_FOUND` |
| `POST .../duplicate` on another user's template | `404 TEMPLATE_NOT_FOUND` |
| `GET .../import-issues` on another user's template | `404 TEMPLATE_NOT_FOUND` |

- The generic `404` means an attacker **cannot distinguish** "exists but not yours" from
  "does not exist". No `403` is used for ownership failures.
- Once the template is verified owned, a child id that does not resolve under it returns
  the child-specific `404` code (`SECTION_NOT_FOUND`, etc.) — these are legitimate-edit
  errors, not existence leaks across users.
- Enforcement layers (defense in depth): (1) application use cases scope every repository
  call by the authenticated `owner_id`; (2) RLS policies enforce the same ownership in
  Postgres (`0002_rls_policies.sql`); (3) the API contract forbids ownership input.
- No `Authorization` header → `401`; ownership failures → `404`. `401` vs `404` is never
  conflated.

---

## 21. Concurrency / Idempotency

- **Concurrency:** last-write-wins. No optimistic locking, no version columns. Edits are
  single-row `UPDATE`s; concurrent edits resolve by final write. This is deliberate for a
  single-inspector-per-template tool and documented. Versioning is deferred unless a real
  collaboration requirement appears.
- **Idempotency (import/duplicate):** not implemented. Repeated `POST /import` and
  `POST /duplicate` calls create **independent new resources** each time. Clients must not
  retry blindly. An idempotency-key mechanism is explicitly deferred unless client retry
  behavior proves to require it — none is assumed today.
- **Conflicts:** `PATCH` renames are naturally idempotent. A rare
  `UNIQUE (template_id, display_order)` collision (only reachable through future reorder
  features, not today's API) is surfaced as `409 DATABASE_CONFLICT`.

---

## 22. Frontend ↔ Backend Boundary

- The frontend holds no knowledge of PostgreSQL, the Supabase schema, RLS, repository
  classes, or any persistence detail. It communicates exclusively through the contracts in
  this document (plus Supabase Auth for obtaining its own token).
- The backend never reads frontend state, cookies, or storage; every request is
  self-contained and authorized by the bearer token (§4).
- The single source of truth for response shapes is §13. The frontend must not depend on
  undocumented fields, and must tolerate unknown-but-documented fields only through the
  documented envelope (`details`).
- DateTime handling: all timestamps UTC (`Z`); the client converts to its local zone.

---

## 23. OpenAPI Mapping

The contract is implementable directly with FastAPI + Pydantic:

- Each endpoint → a typed FastAPI route. Request/response models mirror §12/§13 exactly
  (Pydantic v2, `model_config = ConfigDict(extra="forbid")` so unknown body fields are
  rejected as `VALIDATION_ERROR`).
- File upload → `UploadFile` + `File(...)` with `python-multipart` declared
  (`multipart/form-data`).
- Security scheme → OpenAPI `bearerAuth` (`HTTPBearer`), applied to every route except
  `/health`; production dependency injects the `AuthenticationProvider` and returns
  `UserContext` (401 envelope on failure).
- Path params → `template_id`, `section_id`, `item_id`, `comment_id` as `UUID` typed.
- `404 TEMPLATE_NOT_FOUND` for a missing/foreign template; the same 404 is returned whether
  the resource is absent or foreign (single code path).
- This document is the source; OpenAPI JSON/Swagger is generated, never hand-authored.

---

## 24. Assignment Traceability

| Assignment requirement | Endpoint(s) | Contract support |
| --- | --- | --- |
| Import a Spectora HTML-text export | `POST /templates/import` | §9.3, §18; committed sample fixture |
| Preserve hierarchy | `GET /templates/{id}`, `POST /templates/import` | §13.2 nested shape, §16 |
| Preserve ordering | `GET /templates/{id}`, `POST /templates/import` | §16 explicit orders incl. deterministic tiebreak |
| Preserve comment/content text | `GET /templates/{id}` | `Comment.content` verbatim storage (§13.2, §18) |
| Make unsupported/skipped content visible | `POST /templates/import`, `GET /templates/{id}/import-issues` | `ImportResult.issues`, persistent `import_issues` (§13.4/13.5, §18) |
| Edit section/item/comment text | `PATCH .../sections/{id}`, `.../items/{id}`, `.../comments/{id}` | §10, §12 |
| Persist changes, retrievable after restart | all writes + `GET /templates/{id}` | PostgreSQL-backed repository (§14 of DATABASE_DESIGN) |
| Retrieve templates | `GET /templates`, `GET /templates/{id}` | §9.1, §9.2 |
| Duplicate a template; copy independent of original | `POST /templates/{id}/duplicate` | §17 |
| Authenticated ownership | every endpoint (§4) | Supabase Auth JWT → `UserContext.user_id` = `owner_id` |
| User-level authorization | every `/templates/{id}` endpoint | §5, §20 (owner-scoped, RLS) |

---

## 25. Implemented vs Planned

### CURRENTLY IMPLEMENTED (existing code, not yet this contract)

- `GET /health` — operational probe only (`backend/app/api/routes/health.py`).
- Domain/protocol foundations: `TemplateRepository`, `TemplateImporter`,
  `AuthenticationProvider`, import use case, mock importer, domain models.

### IMPLEMENTED AGAINST THIS CONTRACT

- `POST /api/templates/import` — full §9.3 pipeline: `multipart/form-data` `file`,
  10 MiB cap, extension+content container validation (`415`/`413`), importer-driven
  structure validation (`422 INVALID_XLSX`), atomic persist through an owner-scoped
  repository (in-memory adapter for now; Postgres adapter later), `201 ImportResult`
  with `Location`, and the §14 error envelope (including
  `422 VALIDATION_ERROR` for a missing/malformed request body).
- The error-envelope exception handlers and the bearer-auth dependency
  (`AUTHENTICATION_REQUIRED`/`INVALID_TOKEN`) under the `/api` base path.
- Domain ids/timestamps required by §13 (§27 issue 1 resolution) and the
  `copied_from_id` field on `Template`.
- The repository adapter situation: `insert`, `fetch`, `list`, and issue reads are
  implemented; `update_*`/`duplicate`/`delete` land with their API phases (the in-memory
  adapter raises `NotImplementedError` for them).

### CONTRACT DEFINED FOR NEXT IMPLEMENTATION (to be built against this contract)

- `GET /templates`, `GET /templates/{id}`, `POST /templates/{id}/duplicate`, the three
  PATCH endpoints, `GET /templates/{id}/import-issues`.
- The Postgres repository adapter that backs them.

> Nothing in this section is operational until the backend implementation phase lands.
> This document freezes the target, it does not claim delivery.

---

## 26. Contract Change Policy

- `API-CONTRACTS.md` is the contract. The backend implementation must follow it.
- Once implementation starts, contract changes are deliberate, not incidental:
  1. update this document first and explain **why**;
  2. update the backend;
  3. update frontend integration and tests.
- Breaking change to a live endpoint → introduce it behind `/api/v2` (§3) rather than
  silently changing `/api` semantics.
- The frontend must never depend on behavior that is not documented here; anything
  discovered during implementation that the contract omitted gets documented here before
  it is relied upon.

---

## 27. Consistency Check

Checked against: `docs/DATABASE_DESIGN.md`, `docs/architecture.md` (the repository's
backend-design document), `database/migrations/*`, domain models, protocols, tests, and
`assignment.md`.

### CONTRACT CONSISTENCY ISSUE 1 — domain models lack child IDs

- **File:** `backend/app/domain/models/template.py`
- **Conflict:** `Section`, `Item`, `Comment`, and `CommentOption` have no `id` field, and
  `Template` has no `created_at`/`updated_at`. The API contract (§13) requires ids for
  every nested resource (needed to address the PATCH endpoints after a `GET`) and the
  list/template timestamps.
- **Recommended resolution:** extend the domain dataclasses with optional
  `id: uuid.UUID | None = None` (mirroring `Template.id`) and optional
  `created_at`/`updated_at` on `Template`; the Postgres repository adapter then populates
  them. Smallest change; no schema alteration.
- **Reason:** the schema already has these columns; only the in-memory domain shape is
  missing them, and the API cannot work without IDs.

### CONTRACT CONSISTENCY ISSUE 2 — duplicate default name undefined elsewhere

- **File:** `docs/DATABASE_DESIGN.md` §12 / `backend/app/protocols/repositories/template_repository.py`
- **Conflict:** `duplicate(..., new_name: str | None = None)` has no stated default-name
  rule; the API contract defines `"<source name> (Copy)"` (§12.3, §17).
- **Recommended resolution:** adopt the `" (Copy)"` rule as the documented default in the
  repository contract and implement it in the Postgres adapter.
- **Reason:** the API must specify deterministic naming; the repository signature already
  anticipates a default.

### CONTRACT CONSISTENCY ISSUE 3 — `docs/BACKEND_DESIGN.md` does not exist

- **File:** `docs/`
- **Conflict:** the review expectation references `BACKEND_DESIGN.md`; the actual backend
  design lives in `docs/architecture.md`, which contains no endpoint definitions and
  therefore conflicts with nothing in this contract.
- **Recommended resolution:** none required. Optionally rename/alias
  `docs/architecture.md` as the backend design reference in future docs; not blocking.

### Verified consistent (no change needed)

- Field names: `content` (comment edit), `display_order`, `copied_from_id`, `source`,
  `source_filename`, `owner_id` — match schema, domain, and this contract.
- Enums: `comment_type`, `answer_type`, `option_type`, `issue_type`, `issue_severity` —
  match migration 0001.
- IDOR/ownership: matches `TemplateRepository` owner-scoped methods + RLS §6 of the
  database design.
- Ordering tiebreak for comments (`display_order, id`) matches §20 query patterns.
- Import issues never copied on duplicate matches §12.
- Comment edit uses `content` (the protocol's `update_comment_content`) — not `text`.