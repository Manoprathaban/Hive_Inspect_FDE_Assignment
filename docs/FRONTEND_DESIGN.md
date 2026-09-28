# Frontend System Design

Hive Inspect Template Importer — the React frontend that an inspector uses to import a
Spectora template, view it, edit it, and work with independent copies.

This document is derived from (and must stay consistent with) the repository,
`docs/DATABASE_DESIGN.md`, `docs/API-CONTRACTS.md`, and the assignment. The authoritative
backend surface is `docs/API-CONTRACTS.md`; the frontend never redefines API semantics.

---

## 1. Purpose

The frontend is the desktop web workflow an inspection company uses to carry a
four-year-tuned Spectora template into this product:

- authenticate (Supabase Auth, or the dev stub in development)
- list their templates
- import a Spectora HTML-text spreadsheet export (XLSX)
- view and edit a template's section/item/comment hierarchy in order
- see what was skipped, unsupported, or missing after import
- save edits and reopen to find them persisted
- duplicate a template and edit the copy independently

The frontend does **not** know about PostgreSQL, the Supabase schema, RLS, repository
classes, or XLSX parsing. It talks only to `docs/API-CONTRACTS.md` endpoints over HTTP.

---

## 2. Scope

**In scope:** the five assignment workflows (import, edit/save, duplicate, persistence,
failure handling) plus authentication and import-issue visibility.

**Out of scope (frontend):** everything the assignment excludes — inspection reports,
scheduling, payments, homeowner portals, customer management, analytics, dashboards,
unnecessary AI features, a mobile-specific application, offline-first persistence, and any
browser storage acting as the source of truth.

---

## 3. Technology Stack

What exists today (Lovable-generated bootstrap, verified in the repository):

| Concern | Present | Version | Notes |
| --- | --- | --- | --- |
| Framework | React | 19.2.x | `react` + `react-dom` only |
| Language | TypeScript | ~6.0.2 | strict `tsc -b` via `npm run typecheck` |
| Build/dev | Vite | 8.x | `@vitejs/plugin-react` |
| Styling | Plain CSS | — | CSS custom-property design tokens + nested CSS (`index.css`, `App.css`); light/dark via `prefers-color-scheme` |
| Linting | Oxlint | 1.81.x | `npm run lint` |
| Tests | — | — | no runner installed yet (§27) |

Not present (and **not** required by what exists): Tailwind, shadcn/ui, React Router,
TanStack Query, Zustand/Redux, any component library, any form library, any test runner,
any CSS framework.

### Planned additions (smallest set, justified by the workflow)

| Addition | Why |
| --- | --- |
| `react-router-dom` | The workflow needs 4 navigable locations and deep-linking to a template; a router is the minimal standard way. |
| `@supabase/supabase-js` | Client-side Supabase Auth (login/session); **auth only** — never used for database access (§7). |
| `vitest` + `@testing-library/react` | Planned unit/component tests (§27). Dev-dependency only. |

These are the *minimum*; no other library is introduced without need.

---

## 4. Frontend Architecture

Single-page app, layered from top to bottom. The critical rule: UI never calls
`fetch`/`axios` directly and never touches backend internals.

```
Presentation/UI components            ── views of data + user gestures
        ↓
Feature logic (hooks)                 ── page-level orchestration, validation, mutation calls
        ↓
API client (lib/apiClient.ts)         ── one thin HTTP boundary, follows API-CONTRACTS exactly
        ↓
Server-state layer (lib/query.ts)     ── tiny cache + hooks: fetch, refetch, invalidate
        ↓
FastAPI (docs/API-CONTRACTS.md)
```

Client-side separation:

- **UI components** — render, receive props, emit typed callbacks. No data fetching.
- **Feature/page logic** — custom hooks that own page state, call the API client, own
  loading/error/data exposure.
- **Client-side state** — the tiny server-state cache (§16) + local UI state (editor,
  open dialogs, expansions).
- **API communication** — the single `apiClient` module (§17).
- **Response mapping** — `lib/apiClient.ts` validates against `lib/types.ts` and
  normalizes errors; components receive typed domain objects.
- **Authentication** — Supabase session handled in `features/auth` (hook + provider),
  token injected by the API client (§7, §17).

No Redux or other large state framework: this is a small desktop tool, and every library
decision here is deliberately the smallest appropriate one (see §35).

---

## 5. Project Structure

Kept close to today's layout; only the minimal feature folder is added. `App.tsx` remains
the shell.

```
frontend/
  index.html
  vite.config.ts
  .env.example
  src/
    main.tsx                      # mounts <App/>
    App.tsx                       # shell: providers + router
    index.css                     # design tokens (already present, extended)
    App.css                       # app-wide styles (already present)
    lib/
      apiClient.ts                # HTTP boundary (§17)
      types.ts                    # TS types mirroring API-CONTRACTS §13 (§22)
      errors.ts                   # error normalization + code→message map (§20)
      query.ts                    # minimal server-state hook/cache (§16)
    features/
      auth/
        AuthProvider.tsx          # holds session, exposes useSession()
        loginMachine.ts           # login/logout UI-state logic (§7)
        pages/LoginPage.tsx
      templates/
        types.ts                  # re-export of lib/types.ts scoped to templates
        api.ts                    # functions around lib/apiClient for /templates*
        hooks/useTemplate.ts      # fetch + refetch one template
        hooks/useTemplateList.ts  # fetch + invalidate list
        hooks/useImport.ts        # upload mutation
        hooks/useEditScopes.ts    # PATCH mutations (section/item/comment)
        hooks/useDuplicate.ts     # duplicate mutation
        components/
          TemplateList.tsx
          TemplateCard.tsx
          ImportDialog.tsx
          TemplateViewer.tsx
          SectionView.tsx
          ItemView.tsx
          CommentView.tsx
          InlineTextEditor.tsx
          ImportIssuesPanel.tsx
          IssueBadge.tsx
          DuplicateTemplateDialog.tsx
          states/LoadingState.tsx
          states/ErrorState.tsx
        pages/TemplatesListPage.tsx
        pages/TemplateViewPage.tsx
```

This matches §30 of the brief: feature-oriented where it pays, but no reorganization of
what already exists.

---

## 6. Routes

Minimal set derived from the workflow, not a generic skeleton.

| Route | Purpose | Auth required | Data needed | Loading | Error behavior |
| --- | --- | --- | --- | --- | --- |
| `/` | Redirect to `/templates` (or `/login` when unauthenticated) | no (redirect logic) | — | — | — |
| `/login` | Obtain a session via Supabase Auth (§7) | no | — | spinner while session checks run | inline message on auth failure |
| `/templates` | List the user's templates, import action | yes | `GET /api/templates` summaries | skeleton list | retry state for `500`/network; empty state |
| `/templates/:templateId` | Viewer **and** editor (inline editing, §11) + duplicate, import issues | yes | `GET /api/templates/{id}`, `GET /api/templates/{id}/import-issues` | skeleton of hierarchy | `TEMPLATE_NOT_FOUND` not-found state with back link; retry for transient failures |

Decisions:

- **No separate `/edit` route:** the assignment's core workflow is "view and work with
  the template" — the viewer *is* the editor (inline editing). A dedicated edit page adds
  navigation with no workflow value.
- **No `/import` route:** import is a single-file operation; a modal (`ImportDialog`) on
  `/templates` is simpler and avoids a dead-ending page (§12).
- **No `/duplicate` route:** duplication is an action inside the viewer that navigates to
  the created copy's `/templates/:copyId`.

---

## 7. Authentication

Per `docs/API-CONTRACTS.md` §4, the backend never sees passwords. Login lives on
**Supabase Auth** through `@supabase/supabase-js` (**auth only** — the data API is never
used, so no direct PostgreSQL access exists on the frontend).

- **Login:** the `/login` page offers email/password against Supabase Auth
  (`signInWithPassword`) — or any OAuth provider Supabase is configured with. There is no
  signup form in the app; signup is a Supabase-side concern (the backend migration mirrors
  `auth.users → public.users` automatically).
- **Session:** `AuthProvider` subscribes to `supabase.auth.onAuthStateChange` and exposes
  `useSession()`. The access token (JWT) is held in memory by supabase-js/session; the API
  client reads it per request.
- **Token handling:** `lib/apiClient` attaches `Authorization: Bearer <access_token>`.
  Refresh is delegated to supabase-js.
- **Logout:** `AuthProvider.logout()` calls `supabase.auth.signOut()`, clears the whole
  server-state cache (per-user safety, §16), and routes to `/login`.
- **Unauthenticated redirect:** the router guard (§17 of brief) sends users without a
  session from protected routes to `/login`; returning is a callback param.
- **Expired/invalid session:** any `401` from the API signs out and routes to `/login`
  (a session can be stale even if supabase-js thinks it is fine); users never see a raw
  401.
- **Development:** the backend in `APP_ENV=development` ignores the bearer header
  (`DevAuthProvider`, `API-CONTRACTS` §4). The frontend still runs the same auth flow, but
  with `VITE_SUPABASE_URL` unset it falls back to a **dev session** (deterministic
  placeholder token), so the whole UI is exercisable offline exactly as in production. A
  visible "development" badge distinguishes this mode.

---

## 8. Authorization Boundary

- The frontend never supplies `owner_id`/`user_id` — there is no such field in any request
  (§5 of API contract).
- Hiding a template or disabling a button is **not authorization**. The list simply shows
  what `GET /templates` returns; any attempt on another user's resource returns a generic
  `404 TEMPLATE_NOT_FOUND`, which the frontend maps to the standard not-found state.
- The backend and RLS are authoritative; the frontend only ever acts on the acting user's
  own data because the API only ever returns it.

---

## 9. Template Information Architecture

The hierarchy is rendered exactly as the API returns it (API-CONTRACTS §13.2 / DATABASE
hierarchy): ordered, nested, never flattened.

```
Template: name, source, updated_at, copied_from_id (provenance)
└─ Sections (ordered by display_order)
   └─ Items (ordered by display_order)
      └─ Comments (ordered by display_order, id)
         ├─ content, comment_type, category, answer_type, recommendation, defaults, estimates
         └─ CommentOptions (multiple_choice / unit_type by option_type, display_order)
```

The user can always see: which section an item belongs to, which comments an item has,
comment order, comment type (info / limit / defect), category, options, and the template's
import issues. Order in the UI **is** `display_order`; the UI never re-sorts beyond the
API's documented order.

A single template (measured: 13 sections, 61 items, 392 comments) renders as one page with
three visual columns where practical — Section → Item → Comment — so depth never collapses
into a flat scroll.

---

## 10. Template List

`/templates`, backed by `GET /api/templates` (summaries, newest first by `updated_at`).

- **Loading:** skeleton cards.
- **Empty state:** "No templates yet" + primary "Import a template" action.
- **Card:** template `name`, `source` (small meta label, e.g. *spectora*), `updated_at`
  (localized), and actions **Open** and **Duplicate**.
- **Import action:** card-grid top bar button opens `ImportDialog` (§12).
- **No counts on cards:** the API list returns summaries only (no section/comment counts);
  the frontend does not fire N+1 count calls — §25.
- **Error state:** generic `ErrorState` with retry; `401` routes to login; transient/500
  offers retry.
- Not a dashboard: no charts, no total counts, no navigation beyond the workflow.

---

## 11. Template Viewer / Editor

`/templates/:templateId` is the **core** screen. Layout:

```
Header: template name, source, updated_at, [Duplicate] [Export-issues badge count]
└─ Import issues banner/panel (non-empty only)  ── §13
└─ Section (ordered)
   ├─ Section name (InlineTextEditor on edit) + item count
   └─ Item (ordered)
      ├─ Item name (InlineTextEditor on edit)
      └─ Comment (ordered)
         ├─ Comment name, comment_type / category badge
         ├─ content (InlineTextEditor on edit)  — rendered as plain text (§24)
         └─ options / recommendation / defaults (read-only meta)
```

**Interaction model — inline editing** (chosen over modal/side panel):

- Section/item/comment names and content are always visible; an edit button (pencil) next
  to the text switches that single value into an `InlineTextEditor`.
- Rationale: the assignment is "preserve text and let the inspector keep their work close —
  they will not retype it." Inline keeps context and avoids modal dance for hundreds of
  comments. Modals are reserved for import and duplicate (which are one-shot flows).

No separate "read-only vs edit" page toggle: editing is always available inline, matching a
desk worker who is tuning the template.

---

## 12. Import Experience

One workflow, modal on `/templates`:

```
Select XLSX → client-side checks → Upload (multipart) → backend import
   → 201 ImportResult { template, issues } → navigate to template → issues visible
```

- **Accepted file (client gate):** `.xlsx` extension for usability feedback. The backend is
  authoritative (`415 INVALID_FILE` / `422 INVALID_XLSX`); the client never parses the
  XLSX — the backend owns import semantics.
- **Size feedback:** pre-check against the 10 MiB contract limit before upload
  (`413 FILE_TOO_LARGE` mirrored client-side).
- **Upload/progress:** the dialog shows a "Uploading…" then "Importing…" state; the XHR
  upload progress bar is shown while sending. The request control:
  - field name `file`, `Content-Type: multipart/form-data` per §12.4 of the contract.
- **Success:** navigate to the new template (`ImportResult.template.id`) — do **not**
  rely on the list to have updated (we invalidate `['templates']`).
- **Non-fatal issues:** after navigation the viewer shows the import response banner via
  §13. Import succeeded; issues are informational.
- **Fatal errors:** `INVALID_FILE`, `INVALID_XLSX`, `FILE_TOO_LARGE`, `VALIDATION_ERROR`,
  `INTERNAL_ERROR` → inline error in the dialog with a recoverable message (§20). The user
  stays on `/templates`; nothing partial persists.
- **Missing required source info:** surfaces as `SOURCE_DATA_MISSING` issues, not a
  failure (§13). Distinguishes "missing from the export" from "not supported."

---

## 13. Import Issues

Mandatory visibility — skipped/unsupported content must **never** disappear silently.

Source of truth: `POST /templates/import` → `ImportResult.issues`, and
`GET /templates/{template_id}/import-issues`.

**Display model:**

- **Banner** after a fresh import listing a summary ("3 items were skipped or not
  fully imported") with severity color — required so the user immediately knows to look.
- **Panel** (`ImportIssuesPanel`), on the viewer side rail, listing:
  - `severity` (info/warning/error) as an `IssueBadge`
  - `issue_type` text (`UNSUPPORTED_CONTENT`, `SOURCE_DATA_MISSING`,
    `INVALID_SOURCE_DATA`)
  - `message`
  - `source_field`, `source_row` when present (small mono meta)
  - `raw_value` when present (truncated, escaped — §24)
- Empty issues → no banner/panel; the viewer still offers the panel toggle to re-check.

The panel answers: *"what was not imported, and why?"* — never console-only.

Per-issue `id` is used as React key; `issue_type`/`severity` are enum strings from the
contract and switch UI tone, never free text.

---

## 14. Editing and Persistence

**Save semantics (per API contract):** PATCH endpoints return `204 No Content` — there is
no returned resource. Therefore the frontend's consistent strategy after a successful
mutation is: **apply the optimistic/confirmed value to the local cache immediately, then
refetch the template** (`useTemplate.refetch()`) so the single server source of truth
re-mirrors. See §16.

**Editing behavior (each of section name, item name, comment content):**

| Aspect | Behavior |
| --- | --- |
| Enter edit mode | `InlineTextEditor` activated by pencil button / `Enter` on row focus |
| Validation (client) | `name`: trimmed 1–200 chars; `content`: any length, empty allowed. Mirrors contract §12 exactly. Errors shown inline before submit. |
| Save | PATCH to the contract endpoint with **only** the single field |
| Saving state | editor shows "Saving…", row disabled, no double-submit (button disabled) |
| Success | editor collapses; cache updated; `refetch()` in background; brief "Saved" affordance (toast/checkmark) |
| Cancel | `Esc` or cancel button — draft discarded, **only** if not yet saved |
| Failure | edit input stays open with the user's text (never silently discarded), inline error from §20 (`422 VALIDATION_ERROR`, `404`, `500`); no cache mutation happened |

The frontend **never assumes a save succeeded**: the cache is only updated on a successful
PATCH or the subsequent refetch.

**Persistence UX** (assignment verification): after save, user closes/reloads the tab and
reopens `/templates/:id` — data re-fetches from the backend (no localStorage). The "Saved"
affordance confirms each write; nothing is faked client-side.

---

## 15. Template Duplication

Action: "Duplicate" on a template card (list) or the viewer header. Confirmation dialog
(`DuplicateTemplateDialog`) with a pre-filled name `"<source> (Copy)"` (editable, optional
body field per contract §12.3).

```
Duplicate clicked
  ↓ POST /templates/{id}/duplicate  (optional {"name": ...})
  ↓ 201 → response body = the NEW template (fresh id)
  ↓ Invalidate ['templates'] and ['template', newId] is seeded by the response
  ↓ Navigate to /templates/{newId}
```

- The copy's `id` comes **from the API response** — never guessed.
- The viewer header shows `copied from: <name>` when `copied_from_id` is present, making
  the independent copy legible; all further edits hit only the copy's ids.
- **Failure:** dialog shows §20 error for `404 TEMPLATE_NOT_FOUND`, `500`, etc.; nothing
  navigates; user stays put.

---

## 16. State Management

Two kinds of state, handled separately (per §13 of the brief).

**Server state** (templates, hierarchy, issues, persisted edits) — a tiny bespoke
cache (`lib/query.ts`) built on a context provider + `useSyncExternalStore`-style
subscriptions, like:

```
query keys: ['templates']
            ['template', templateId]
            ['import-issues', templateId]
```

- **Fetch:** `useQuery(key, fetcher)` → `{ data, isLoading, error, refetch }`.
- **Mutation:** `useMutation(...)` runs the API call; on success it may write the response
  into the cache and/or **invalidate** related keys (list after import/duplicate; the
  template after a PATCH → refetch).
- **Stale time:** short (e.g. 30 s) for the template hierarchy; list refetched on mount
  and after mutations. Not aggressively cached — data is small.
- **Ownership safety:** the cache lives under `AuthProvider`; **logging out clears the
  entire cache** so no data can cross users. Keys are never global across sessions.

**UI state** — React local state per component / page: active editor, draft text, expanded
sections, open dialogs, upload progress, selected tab. No global store; nothing here needs
it at this scale.

TanStack Query was evaluated. For one-lane desktop usage with a handful of keys, a
dependency-free hook with invalidation is the smallest appropriate solution (§35). If the
app later grows multi-view caching demands, TanStack Query is the drop-in replacement
behind the same `lib/query.ts` interface — deferred, not promised.

---

## 17. API Client

Single HTTP boundary (`lib/apiClient.ts`), used by `features/templates/api.ts`; no
component calls `fetch` directly.

- **Base URL:** `VITE_API_BASE_URL` (default `http://localhost:8000`), resolved once.
- **Authentication headers:** `Authorization: Bearer <token>` from the current session
  (§7); absent in dev fallback mode.
- **Request serialization:** JSON for PATCH/POST bodies; `FormData` with field `file` for
  import. Pydantic `extra="forbid"` means the client sends exactly the contract fields.
- **Response parsing:** JSON decoded then **validated** against `lib/types.ts` guards
  (lightweight) so the UI only ever sees contract-shaped data.
- **Error normalization:** non-2xx → `ApiError { code, message, details, status }` parsed
  from the contract envelope `{"error": {...}}` (§20). Network/timeout → synthetic
  `NETWORK_ERROR` code.
- **Timeout:** fetch aborts after 30 s; uploads get a longer ceiling (60 s) with progress.
- **File upload:** `FormData`, only `POST /templates/import`, progress events for the
  dialog; never stored client-side after the request.

The sole contract for every call is `docs/API-CONTRACTS.md` (§18 mapping is exact).

---

## 18. API Contract Mapping

Every backend interaction corresponds 1:1 to `API-CONTRACTS.md`. None invented.

| UI need | Method + path | Request | Response used |
| --- | --- | --- | --- |
| Template list / cards | `GET /api/templates` | — | `TemplateSummary[]` (name, source, updated_at, id) |
| Viewer load | `GET /api/templates/{template_id}` | — | `Template` (full hierarchy, §13.2) |
| Import | `POST /api/templates/import` | `multipart`, field `file` | `ImportResult.template` + `.issues` |
| Duplicate | `POST /api/templates/{template_id}/duplicate` | optional `{"name"}` | new `Template` (id to navigate) |
| Rename section | `PATCH /api/templates/{template_id}/sections/{id}` | `{"name"}` | `204` → refetch |
| Rename item | `PATCH /api/templates/{template_id}/items/{id}` | `{"name"}` | `204` → refetch |
| Edit comment | `PATCH /api/templates/{template_id}/comments/{id}` | `{"content"}` | `204` → refetch |
| Import issues | `GET /api/templates/{template_id}/import-issues` | — | `ImportIssue[]` |
| Not used | `DELETE /templates/{id}` | — | not in contract (§8) → not in UI |

No **API CONTRACT GAP** exists: every planned UI operation maps to a documented endpoint,
and operations without endpoints (e.g. renaming a whole template — the assignment only
asks for section/item/comment edits) are intentionally absent from the UI.

---

## 19. Loading States

Intentional state for every async op; the same mutable action is disabled while in-flight
(preventing duplicate requests):

| Operation | Presentation |
| --- | --- |
| Template list | skeleton cards |
| Template load | skeleton of section rows |
| Import — uploading | dialog progress bar |
| Import — processing | dialog "Importing…" (non-cancellable state) |
| Rename section/item/comment | editor `Saving…`, row disabled |
| Duplication | dialog busy state, buttons disabled |
| Import issues | panel skeleton when opened |

Loading is per-flow, not a full-screen spinner, so the hierarchy stays visible during
background refetches (which show no new spinner).

---

## 20. Error Handling

One normalization path: `lib/errors.ts` maps every contract error code to a user-facing
message and, where useful, a recovery hint. Never raw stack traces.

| Code / status | User-facing behavior |
| --- | --- |
| `401 AUTHENTICATION_REQUIRED` / `INVALID_TOKEN` | route to `/login`, clear session + cache |
| `403 FORBIDDEN` | not expected (contract reserves it) → generic "You can't do that" with reload/back |
| `404 TEMPLATE_NOT_FOUND` / SECTION/ITEM/COMMENT_NOT_FOUND | not-found panel ("This template isn't available anymore") with back to `/templates`; an edit 404 keeps the draft + message |
| `409 DATABASE_CONFLICT` | rare → "The change wasn't saved. Reload and try again." |
| `422 VALIDATION_ERROR` | inline field message from `details` (bad name/content) |
| `413 FILE_TOO_LARGE` | import dialog: "File exceeds the 10 MiB limit." |
| `415 INVALID_FILE` | import dialog: "That doesn't look like a Spectora export." |
| `422 INVALID_XLSX` | import dialog: "The file could not be read as a valid XLSX." |
| `500 INTERNAL_ERROR` / `NETWORK_ERROR` | generic retry message with a Retry button |
| Import issues (`UNSUPPORTED_CONTENT` etc.) | **not errors**: §13 banner/panel |

Mapped messages live in one table in `lib/errors.ts` so copy is consistent.

---

## 21. Component Architecture

Components map to real responsibilities; none exist for ceremony.

| Component | Responsibility | Props in | Actions out |
| --- | --- | --- | --- |
| `TemplateList` | grid/list of cards | `items: TemplateSummary[]`, loading/error | `onOpen(id)`, `onDuplicate(s)`, `onImport()` |
| `TemplateCard` | one card | `summary` | `onOpen`, `onDuplicate` |
| `ImportDialog` | file pick + validation + progress + errors (§12) | `open`, `onClose` | `onImported(templateId)` |
| `TemplateViewer` | renders header + hierarchy + issue panel | `template`, `issues`, status | `onEdit(...)`, `onDuplicate` |
| `SectionView` / `ItemView` / `CommentView` | ordered nested rows | typed child (or list) + callbacks | `onRename(name)`, `onEditContent(content)` |
| `InlineTextEditor` | inline edit field on one value, single source of truth for validation/save/cancel (§14) | `value`, `onSave(v)`, `onCancel`, `saveState`, mode (`name`/`content`) | `onSave`, `onCancel` |
| `ImportIssuesPanel` | issue list §13 | `issues: ImportIssue[]`, `open` | `onClose` |
| `IssueBadge` | severity/type chip | `issue` | — |
| `DuplicateTemplateDialog` | confirm + optional name | `template`, `open` | `onDuplicated(templateId)`, `onCancel` |
| `LoadingState` / `ErrorState` | shared async chrome | variants, retry cb | `onRetry` |

`InlineTextEditor` owns draft text so editing state never leaks into the viewer; the page
hook owns server mutation state.

---

## 22. Type System

Types are a **direct transcription** of `API-CONTRACTS.md` §13 (snake_case preserved;
no second, divergent representation). Single source at `lib/types.ts`; `features/*` import
from it.

```ts
type UUID = string
type DateTime = string            // RFC 3339 UTC
type CommentType = 'info' | 'limit' | 'defect'
type AnswerType = 'boolean' | 'checkbox' | 'date' | 'number' | 'range' | 'text'
type OptionType = 'multiple_choice' | 'unit_type'
type IssueType = 'SOURCE_DATA_MISSING' | 'UNSUPPORTED_CONTENT' | 'INVALID_SOURCE_DATA'
type IssueSeverity = 'info' | 'warning' | 'error'

interface TemplateSummary {
  id: UUID; name: string; source: string
  source_filename: string | null; created_at: DateTime; updated_at: DateTime
}
interface Template {
  id: UUID; name: string; source: string
  source_filename: string | null; copied_from_id: UUID | null
  created_at: DateTime; updated_at: DateTime
  sections: Section[]
}
interface Section { id: UUID; name: string; display_order: number; items: Item[] }
interface Item { id: UUID; name: string; display_order: number; comments: Comment[] }
interface Comment {
  id: UUID; name: string; content: string
  comment_type: CommentType; category: number | null; answer_type: AnswerType
  display_order: number
  recommendation: string | null; default_value: string | null
  default_value_2: string | null; default_unit_type: string | null
  estimate_min: number | null; estimate_max: number | null; source_row: number | null
  options: CommentOption[]
}
interface CommentOption { option_type: OptionType; value: string; display_order: number }
interface ImportIssue {
  id: UUID; issue_type: IssueType; severity: IssueSeverity; message: string
  source_row: number | null; source_field: string | null; raw_value: string | null
}
interface ImportResult { template: Template; issues: ImportIssue[] }
interface ApiErrorShape { error: { code: string; message: string; details: unknown } }
```

- Ordering contract (§16 of API) is honored by rendering arrays as received.
- OpenAPI-driven codegen is **deferred/optional**, not configured; if introduced later it
  must produce exactly these shapes.

---

## 23. Security

- **No secrets in the client:** no PostgreSQL credentials, no Supabase `service_role` key,
  no backend private keys. `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` are **public
  client-safe** values only; the anon key is never used against the data API.
- **Client authorization is not real authorization:** hiding controls is UX, enforcement
  is the backend + RLS. Never refuted by the frontend.
- **XSS-safe rendering:** comment `content` is rendered as **text** (React escapes);
  markup is never injected with `dangerouslySetInnerHTML` in v1 (§24).
- **Links:** any URL-looking text remains inert text. If clickable links were added later,
  they must be validated (`http`/`https` only, `rel="noopener"`, target checks) — deferred.
- **Upload restrictions:** file input `accept=".xlsx"`; size and type re-checked client
  side; backend remains authoritative.
- **Token handling:** held by supabase-js (memory/refresh), sent only to `VITE_API_BASE_URL`;
  never logged, never stored in localStorage by us, cleared on logout.

---

## 24. Spectora Content Handling

Measured facts the UI is designed around (from the committed export:
`docs/DATABASE_DESIGN.md` §16): comment text may contain XML-decoded markup and links
(91/392 rows had text; 34 had markup; longest 701 characters).

- **v1 rendering policy: comment `content` is displayed as plain text.** The backend
  preserves markup verbatim in the DB; displaying it as text guarantees nothing is
  executed or injected. `white-space: pre-wrap` preserves author line breaks.
- **Links:** presented as text (not anchors) in v1 — safest with zero feature loss for
  the assignment (the workflow is template *editing*, not web publishing).
- **Unsupported formatting:** anything the model cannot represent already surfaces as
  `UNSUPPORTED_CONTENT` issues (§13); the UI never claims full rich-text preservation.
- **Rich rendering (sanitized)** is explicitly **deferred**: if a need appears, it must
  go through a sanitizer (allowlist of tags/attrs, link protocols) before render — never
  direct HTML injection. Documented here so it is a deliberate change, not an accident.

---

## 25. Performance

The real target dataset is small (13 sections / 61 items / 392 comments / ≤ ~700-char
content); no aggressive engineering for this scale (§25 of brief — don't optimize
prematurely).

- **One hierarchy fetch per template** (`GET /templates/{id}`) — no N+1; the API returns
  the complete aggregate (per §16/§19 of API contract).
- **No count N+1:** the list page shows only what `TemplateSummary` provides rather than a
  count query per card.
- **Render efficiency:** hierarchy components are memoized (`React.memo`) on their typed
  props so editing one comment re-renders only that subtree; inline editor keeps local
  draft state so typing doesn't re-render the whole page.
- **Refetch separation:** background refetch after mutations re-renders the cache consumer
  without blocking the input being edited.
- **Lazy loading:** deferred — the entire app is small; code-split routes only if the
  bundle asks for it (not now).
- **Browser persistence:** never used as a substitute for backend persistence.

---

## 26. Accessibility

Basic, cost-effective accessibility (no elaborate framework; §23 of brief):

- Keyboard: all controls focusable; `Enter` opens an editor, `Esc` cancels; visible focus
  rings (reusing the existing `:focus-visible` token style).
- Labels: every input (including the inline editors and file input) has an associated
  `<label>` or `aria-label`.
- Semantic controls: real `<button>`, `<input>`, `<textarea>`; headings for template
  name/section names.
- Error text is readable and associated (`aria-describedby`).
- Issue badges distinguish by **icon + color + text**, not color alone (warning contrast
  against the token palette).
- Modal dialogs (import, duplicate) trap focus, restore focus on close, and dismiss on
  `Esc`.

---

## 27. Testing Strategy

**Currently implemented:** none (verified — `package.json` has no test runner). Not claimed
below.

**Planned (added with `vitest` + `@testing-library/react`, dev-only):**

- **Unit:** `lib/errors.ts` code→message mapping; validation rules for `name`/`content`;
  `lib/query.ts` key/invalidation logic; type guards.
- **Component:** `InlineTextEditor` (save/cancel/loading/failure preserve-draft),
  `ImportIssuesPanel`, `ImportDialog` error states, `LoadingState`/`ErrorState`.
- **API integration:** `features/templates/api.ts` against mocked `fetch`
  (request shape, auth header, `204` handling, error normalization).
- **E2E (optional, if time allows):** the five acceptance flows (§28) via Playwright
  against the real backend + seeded template.

Nothing is claimed as shipped until the test files exist and pass.

---

## 28. User Flows

Mapping directly to assignment verification.

**FLOW 1 — IMPORT:** Login → `/templates` → Import → `.xlsx` → upload/processing → new
template opens → issue banner if any → issues panel readable.

**FLOW 2 — EDIT + PERSISTENCE:** Open template → rename section (save) → rename item
(save) → edit comment content (save) → "Saved" affordance → reload tab → reopen
`/templates/:id` → all edits present (from backend).

**FLOW 3 — DUPLICATE:** Open original → duplicate → dialog (name `"(Copy)"`) → navigate to
copy → edit copy (save) → open original → original unchanged.

**FLOW 4 — FAILURE:** Upload a malformed/`non-xlsx` file → dialog inline error
(§20), nothing partial persisted.

**FLOW 5 — UNSUPPORTED CONTENT:** Import valid template with unsupported columns →
`UNSUPPORTED_CONTENT` issue visible with field/row/value → user understands what was
skipped and why.

---

## 29. Data Flow Diagrams

**A. Authentication**
```
Browser user → /login → supabase-js (Auth) → session (JWT)
     → AuthProvider (useSession) → apiClient attaches bearer → /templates
```

**B. Template list**
```
/ │ templates page → useTemplateList → apiClient.get('/templates')
     → FastAPI → PostgreSQL → TemplateSummary[] → cache ['templates'] → TemplateList cards
```

**C. Template loading**
```
/templates/:id → useTemplate → GET /templates/{id} (+ import-issues when panel opens)
     → cache ['template', id] → TemplateViewer (sections→items→comments, in display_order)
```

**D. Import**
```
Dialog → File → apiClient.upload multipart 'file' → POST /templates/import
     → FastAPI (import + persist atomically) → 201 ImportResult
     → cache['template', newId] = template; issues to banner; invalidate ['templates']
     → navigate /templates/newId
```

**E. Edit/save**
```
InlineTextEditor → validation → PATCH .../sections|items|comments/{id} {name|content}
     → 204 → apply value to cache → refetch ['template', id] → UI "Saved"
      └ (non-2xx) → keep draft + inline error; no cache change
```

**F. Duplicate**
```
Duplicate button → dialog (optional name) → POST /templates/{id}/duplicate
     → 201 Template (fresh id) → invalidate ['templates'] → navigate /templates/{newId}
```

**G. Import issue display**
```
Import result .issues, or GET /templates/{id}/import-issues
     → cache ['import-issues', id] → ImportIssuesPanel rows (severity/type/message/meta)
```

---

## 30. Deployment

```
Browser
   ↓
Vercel (frontend SPA)      ← VITE_API_BASE_URL → FastAPI backend (Render)
                               ↓
                          Supabase PostgreSQL  +  Supabase Auth
```

- **Frontend target: Vercel** (already selected; `frontend/README.md` documents framework
  preset Vite, build output `dist/`).
- Env vars at build time: `VITE_API_BASE_URL` (production backend URL), and in production
  auth mode `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` (public only).
- No private backend credentials in the frontend; CORS is handled by the backend
  (already configured, `backend/app/main.py`).

---

## 31. Environment Configuration

Public-only values, no secrets, `.env.example` maintained:

| Variable | Dev | Production | Notes |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000` (default) | deployed API URL | required |
| `VITE_SUPABASE_URL` | unset → dev-auth fallback (§7) | Supabase project URL | public |
| `VITE_SUPABASE_ANON_KEY` | unset | Supabase anon (public) key | public; never the service-role key |

---

## 32. Implemented vs Planned

### CURRENTLY IMPLEMENTED
- React 19 + TS + Vite bootstrap (single `App.tsx` placeholder page, `index.css` design
  tokens, light/dark, `VITE_API_BASE_URL` on the page).
- Build/typecheck/lint commands only. No routes, no API client, no auth, no components,
  no tests.

### DESIGNED / NEXT IMPLEMENTATION
- Everything in this document: router + routes (§6), auth provider (§7), API client (§17),
  server-state cache (§16), template list/import/viewer/editor (§10–§12), issue panel
  (§13), duplication (§15), types (§22), tests (§27).

### DEFERRED (explicitly not in v1)
- Sanitized rich-HTML rendering of comment content (§24).
- Clickable link rendering; code-split lazy loading; TanStack Query (behind `lib/query.ts`);
  OpenAPI type codegen; Playwright E2E suite; template *rename* (no endpoint requested by
  the assignment).

---

## 33. Assignment Traceability

| Assignment requirement | Frontend support | Status |
| --- | --- | --- |
| Import Spectora XLSX | `ImportDialog` → `POST /templates/import` (§12, §18) | Designed |
| Preserve hierarchy | Viewer renders nested sections→items→comments (§9, §11) | Designed |
| Preserve ordering | Arrays rendered in `display_order` as returned (§9, §16) | Designed |
| Preserve comment/content text | `content` shown verbatim as text; markup preserved by backend (§14, §24) | Designed |
| Unsupported/skipped content visible | Import issues banner + panel, never silent (§13) | Designed |
| Edit section/item/comment | inline editors → PATCH (§14) | Designed |
| Persistence across close/reopen | server-backed refetch, no localStorage (§14, §16) | Designed |
| Duplicate template | `DuplicateTemplateDialog` → `POST duplicate` (§15) | Designed |
| Independent copies | navigation to fresh response id; edits hit copy ids (§15, §22) | Designed |
| Authentication | Supabase Auth session → bearer header (§7) | Designed |
| Failure handling | single error mapping, recovery states, FLOW 4 (§20, §28) | Designed |

---

## 34. Out of Scope

Frontend explicitly does **not** build: inspection reports, scheduling, payments,
homeowner portal, customer management, analytics, dashboards, unnecessary AI features, a
mobile-specific application, offline-first persistence, or any browser storage as the
source of truth (§2).

---

## 35. Design Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | No TanStack Query — small custom `lib/query.ts` | One-lane desktop flow, handful of keys; dependency-free meets "smallest appropriate solution"; drop-in swap possible later. |
| D2 | No Redux/Zustand/Context-global UI store | UI state is per-component; a global store adds coupling without need. |
| D3 | Inline editing rather than modal/side-panel | Cheap to start, keeps hierarchy context; matches "they will not retype it". |
| D4 | Viewer == editor, no separate edit route | The assignment treats viewing/working-with as one step; extra routes add navigation with no workflow gain. |
| D5 | Import & duplicate as dialogs, not routes | One-shot flows; avoids dead-end pages and keeps URL state minimal (only `templateId`). |
| D6 | Comment content rendered as text in v1 | Safest handling of Spectora markup; rich rendering is a deliberate, deferred, sanitized change (§24). |
| D7 | Refetch-after-save instead of trusting a mutation response | PATCH is `204` per contract; refetching keeps the backend as the only truth. |
| D8 | Dev auth fallback mirrors real flow | Lets the whole UI be exercised offline with the `DevAuthProvider` backend, identical to production wiring. |
| D9 | Keep plain-CSS token system; no Tailwind/shadcn | Existing Lovable styling is pastel tokens + color-scheme; adding a framework would replace existing work without requirement. |
| D10 | No template-rename UI | The API contract has no such endpoint and the assignment doesn't ask for it (§18). |

---

## 43-appendix. Consistency Review

`FRONTEND_DESIGN.md` was checked against `DATABASE_DESIGN.md`, `API-CONTRACTS.md`, and the
existing code. Results:

**Verified consistent:** endpoint methods/paths (§18) match the contract table; request
field names `name`/`content` (not `text`); response field names incl. `source_filename`,
`copied_from_id`, `comment_type`, `answer_type`, `display_order`, `source_row`; error
envelope and code set; bearer auth model; hierarchy and ordering semantics (`display_order`
at each level, comment `(display_order, id)` tiebreak — invisible to UI but preserved);
import-issue types/severities; duplicate returns a new template with fresh id and does not
copy issues; ownership never client-supplied; no client-side DELETE usage.

**No FRONTEND DESIGN CONSISTENCY ISSUES** requiring a change to `API-CONTRACTS.md`. One
design consequence documented rather than hidden: PATCH returns `204` (no body), so the
frontend uses apply-and-refetch (`§14`, `D7`) — this is consistent with the contract, not a
conflict.