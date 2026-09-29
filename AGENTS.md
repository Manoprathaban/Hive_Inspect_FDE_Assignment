# Hive Inspect — Implementation Protocol

You are the primary implementation agent for the Hive Inspect FDE Assignment.

This document is the DEFAULT ENGINEERING PROTOCOL for every implementation task in this repository.

Once this protocol is established, individual task prompts only need to identify the feature to implement.

Example:

    Implement feature: Spectora XLSX importer

or:

    Implement feature: Template editor API

You MUST follow all rules in this document for every implementation task.

============================================================
0. SOURCE OF TRUTH
============================================================

Before implementing ANY feature, inspect the following in this order:

1. Assignment requirements
2. docs/DATABASE_DESIGN.md
3. docs/BACKEND_DESIGN.md
4. docs/API-CONTRACTS.md
5. docs/FRONTEND_DESIGN.md
6. README.md
7. NOTES.md
8. Existing source code
9. Existing tests
10. Existing migrations
11. Existing Git history where useful

These documents define the intended architecture.

Do NOT invent architecture while implementing.

If implementation requirements conflict with documentation:

STOP and report:

DESIGN CONFLICT

Include:

- conflicting files
- conflicting statements
- impact
- recommended resolution

Do not silently override an established design.

============================================================
1. IMPLEMENTATION ORDER
============================================================

The project is implemented in controlled stages.

Current intended order:

PHASE 1
Database/schema implementation
        ↓
PHASE 2
Backend/domain/application implementation
        ↓
PHASE 3
REST API implementation
        ↓
PHASE 4
Frontend implementation
        ↓
PHASE 5
Integration
        ↓
PHASE 6
CI/CD + deployment validation
        ↓
PHASE 7
Final assignment verification

Do not jump ahead unless the task explicitly requires it.

If a feature depends on another incomplete feature:

identify the dependency.

Do not implement unrelated future functionality just because it is convenient.

============================================================
2. FEATURE BRANCH RULE
============================================================

Every meaningful implementation task must use a dedicated short-lived feature branch.

Branch naming:

feature/<short-description>
fix/<short-description>
refactor/<short-description>
chore/<short-description>
test/<short-description>

Examples:

feature/schema-implementation
feature/spectora-importer
feature/template-repository
feature/template-api
feature/authentication
feature/template-editor
feature/frontend-integration

Before creating a branch:

1. Check current git status.
2. Check current branch.
3. Fetch latest origin.
4. Ensure no unrelated uncommitted work will be overwritten.
5. Ensure main is up to date.
6. Create the branch from the latest main.

Do NOT create branches for:

- individual files
- individual functions
- individual tables
- tiny fixes
- trivial formatting changes

One branch should represent one meaningful deliverable.

============================================================
3. PROTECT MAIN
============================================================

Never:

- force push main
- rewrite main history
- reset main destructively
- commit unfinished implementation directly to main

All implementation work happens on the feature branch.

Main must remain buildable and testable.

============================================================
4. BEFORE CODING
============================================================

Before writing code:

1. Understand the feature.
2. Inspect existing implementation.
3. Identify affected modules.
4. Identify dependencies.
5. Check relevant API contracts.
6. Check database schema.
7. Check existing tests.
8. Create an implementation plan.

The plan should be concise.

Do not produce an enormous plan for a small feature.

Then implement.

============================================================
5. MINIMAL CHANGE PRINCIPLE
============================================================

Implement only what is required for the requested feature.

Do NOT:

- refactor unrelated modules
- rename unrelated files
- change established architecture unnecessarily
- add speculative abstractions
- add unused dependencies
- add unnecessary libraries
- add unnecessary caching
- add Redis
- add Kafka
- add microservices
- add Kubernetes
- add background workers
- add AI
- add analytics

unless explicitly required by the assignment/task.

Prefer the smallest production-quality implementation.

============================================================
6. ARCHITECTURE RULES
============================================================

Maintain the documented dependency direction:

Frontend
    ↓
API
    ↓
Application
    ↓
Domain / Protocols
    ↓
Adapters
    ↓
Infrastructure
    ↓
PostgreSQL / Supabase

Domain/application code must NOT directly depend on:

- FastAPI
- Supabase SDK
- PostgreSQL implementation details
- XLSX parsing libraries
- Gemini SDK
- frontend frameworks

Source-specific logic must stay behind the appropriate protocol/adapter.

For example:

TemplateImporter
    ↑
    |
SpectoraXlsxImporter

The application must depend on TemplateImporter, not directly on SpectoraXlsxImporter.

============================================================
7. DATABASE IMPLEMENTATION
============================================================

For database tasks:

1. Read docs/DATABASE_DESIGN.md.
2. Read existing migrations.
3. Use versioned migrations.
4. Never manually mutate the database without a migration.
5. Preserve foreign keys.
6. Preserve constraints.
7. Preserve indexes.
8. Preserve RLS.
9. Preserve ownership semantics.
10. Preserve explicit ordering.

Database is the persistent source of truth.

Do NOT use:

localStorage
sessionStorage
IndexedDB

as primary persistence.

Any schema change must be:

- justified
- migrated
- documented
- tested where possible

Do not add tables unless required.

============================================================
8. RLS / SECURITY
============================================================

Supabase PostgreSQL uses RLS.

Never disable RLS simply because the backend exists.

Every user-owned operation must be owner-scoped.

Identity comes from:

UserContext.user_id

Never trust owner_id/user_id supplied by the client.

For nested resources verify ownership through the parent hierarchy.

Example:

comment
 ↓
item
 ↓
section
 ↓
template
 ↓
owner

Application authorization and RLS are defense in depth.

============================================================
9. BACKEND IMPLEMENTATION
============================================================

Backend implementation must follow:

docs/BACKEND_DESIGN.md

and:

docs/API-CONTRACTS.md

Do not invent endpoints.

Do not expose raw database CRUD unless the API contract requires it.

Use:

API
 ↓
Application use case
 ↓
Protocol
 ↓
Adapter
 ↓
Database

Use dependency injection where appropriate.

Keep FastAPI-specific code at the API boundary.

============================================================
10. API CONTRACT RULE
============================================================

docs/API-CONTRACTS.md is authoritative.

For every API implementation:

- HTTP method must match.
- Path must match.
- Request schema must match.
- Response schema must match.
- Authentication requirements must match.
- Error contract must match.
- Status codes must match.

Do NOT silently change the API contract.

If the implementation reveals a genuine problem:

STOP and report:

API CONTRACT GAP

Do not redesign the API while implementing it.

============================================================
11. FRONTEND IMPLEMENTATION
============================================================

Frontend implementation must follow:

docs/FRONTEND_DESIGN.md

and:

docs/API-CONTRACTS.md

The frontend must communicate through the backend API.

Do NOT:

- connect directly to PostgreSQL
- query Supabase PostgreSQL directly
- bypass the API
- implement RLS logic in the frontend
- duplicate backend business rules unnecessarily

Server state and UI state must remain conceptually separate.

============================================================
12. IMPORTER IMPLEMENTATION
============================================================

For Spectora importer work:

Use the committed Spectora XLSX as the canonical test artifact.

Do not replace it with a fabricated dataset.

The importer must:

- validate workbook
- validate expected structure
- map supported fields
- preserve hierarchy
- preserve text/content
- preserve deterministic ordering
- identify unsupported content
- identify source-data-missing information
- avoid silent data loss
- handle malformed input safely

Distinguish:

SOURCE_DATA_MISSING

from:

UNSUPPORTED_CONTENT

Do not silently discard source information.

Do not allow Spectora-specific logic to leak into domain/application layers.

============================================================
13. PERSISTENCE
============================================================

All persistent application data must go through the backend/database.

A successful mutation is not considered complete until the persistence operation succeeds.

Frontend must not optimistically claim:

"Saved"

before receiving successful backend confirmation.

============================================================
14. TEMPLATE DUPLICATION
============================================================

Template duplication must create independent records.

A copy must have independent IDs for:

- template
- sections
- items
- comments
- comment options

where applicable.

Preserve:

- hierarchy
- ordering
- content

Use a transaction.

Either:

entire copy succeeds

OR:

no partial copy remains.

============================================================
15. TESTING IS REQUIRED
============================================================

Every feature must include tests.

Do not treat testing as a final optional step.

For every implementation determine:

Unit tests
Integration tests
API tests
Frontend tests
E2E tests

as applicable.

At minimum test the feature's critical behavior.

Tests must cover:

- happy path
- validation failure
- authorization failure where applicable
- not-found behavior where applicable
- important edge cases
- persistence behavior where applicable

Do not write meaningless tests just to increase coverage.

Tests must verify actual behavior.

============================================================
16. TEST COVERAGE
============================================================

Run coverage for backend code.

Use the repository's existing coverage configuration if present.

If none exists, use an appropriate Python coverage tool such as:

pytest --cov

Target:

meaningful coverage of changed code and critical paths.

Do not chase an artificial 100% number.

However, new production logic should not be left untested.

Report:

- total coverage
- changed-code coverage if available
- uncovered important paths

If coverage is poor because the environment lacks external services, document the limitation.

============================================================
17. PYTHON QUALITY
============================================================

For Python code, run:

ruff check .

and if configured:

ruff format --check .

If formatting is required:

ruff format .

Do not suppress Ruff errors without understanding them.

Do not add blanket noqa comments merely to make CI pass.

Fix the underlying issue whenever practical.

Also run:

pytest

and:

pytest --cov

where applicable.

============================================================
18. TYPE CHECKING
============================================================

If the repository uses a type checker such as:

mypy
pyright

run the configured checker.

Do not introduce a new type-checking system unless required.

Fix type errors caused by the implementation.

============================================================
19. FRONTEND QUALITY
============================================================

Before considering frontend work complete, run the project's configured:

- lint
- typecheck
- tests
- build

Typical commands may include:

npm run lint
npm run typecheck
npm test
npm run build

BUT:

Use the actual commands defined in package.json.

Never invent commands if the project uses different scripts.

============================================================
20. SCHEMATHESIS
============================================================

For API implementation work, Schemathesis validation is REQUIRED.

The API contract/OpenAPI schema must be exercised against the running API.

Use the project's configured Schemathesis command if one exists.

If none exists, determine the simplest appropriate command based on the actual FastAPI/OpenAPI setup.

Schemathesis should validate:

- documented endpoints
- request schemas
- response schemas
- status codes
- malformed inputs
- boundary values
- contract compatibility

Do NOT treat Schemathesis as a replacement for business-logic tests.

Use both:

pytest

and:

Schemathesis

For API features.

If Schemathesis cannot run because a required external service is unavailable:

- do not fake success
- document exactly why
- run all tests that can run locally
- report the blocked validation

============================================================
21. DATABASE TESTING
============================================================

If a real PostgreSQL/Supabase test environment is available:

run:

- migrations
- schema validation
- FK tests
- RLS tests
- ownership tests
- cascade tests
- transaction tests

Verify:

User A cannot access User B's data.

If no live database is available:

do not claim these tests passed.

Run static validation where possible and report the limitation.

============================================================
22. TEST DATA
============================================================

Use the actual committed Spectora XLSX for importer integration tests.

Do not create an unrelated fake template as the primary integration fixture.

Small synthetic fixtures may be used for:

- malformed input
- edge cases
- focused unit tests

but the real Spectora export must remain part of integration verification.

============================================================
23. ERROR HANDLING
============================================================

Never swallow exceptions silently.

Do not use:

except Exception:
    pass

unless there is a very specific and documented reason.

Map expected errors to the documented API error contract.

Never expose:

- stack traces
- database credentials
- JWTs
- service-role keys
- internal secrets

to API clients.

============================================================
24. LOGGING
============================================================

Use structured/useful logging where appropriate.

Do not log:

- passwords
- access tokens
- service-role credentials
- sensitive environment values

Avoid noisy debug logging in production paths.

============================================================
25. CONFIGURATION
============================================================

Use environment variables/configuration for:

- database connection
- Supabase configuration
- API URL
- authentication
- CORS
- deployment settings

Never hardcode secrets.

Never commit:

.env

or credentials.

Maintain/update:

.env.example

if appropriate.

============================================================
26. CI/CD
============================================================

The repository must eventually have automated CI/CD.

CI must validate the same quality gates used locally.

At minimum evaluate separate workflows for:

Frontend
Backend
Database/migrations

Use path-based execution where appropriate.

For example:

frontend changes
    ↓
frontend CI

backend changes
    ↓
backend CI

database changes
    ↓
database migration validation

Do not deploy database changes as arbitrary scripts.

Use versioned migrations.

CI must NOT expose secrets in logs.

Deployment secrets belong in the CI/CD secret store.

============================================================
27. LOCAL QUALITY GATE
============================================================

Before a feature branch can be considered complete, run all applicable checks.

Backend:

1. pytest
2. pytest --cov
3. ruff check
4. ruff format --check
5. type checker if configured
6. API tests
7. Schemathesis for API features
8. database validation where applicable

Frontend:

1. lint
2. typecheck
3. tests
4. build

Integration:

1. backend starts
2. frontend starts
3. API contract works
4. critical user flow works

Do not skip a relevant check merely because the feature "looks correct."

============================================================
28. FAILURE HANDLING
============================================================

If any quality gate fails:

DO NOT commit/push the feature as complete.

Fix the issue.

Then rerun the failed check.

If the failure is caused by an environmental limitation:

document:

CHECK BLOCKED

- command
- reason
- environment limitation
- what was successfully validated

Never report a blocked check as passed.

============================================================
29. GIT COMMIT STRATEGY
============================================================

Use meaningful commits.

Examples:

feat: implement Spectora template importer
feat: add template repository
feat: add template import API
test: add importer integration coverage
fix: preserve deterministic comment ordering
refactor: isolate Spectora mapping adapter

Do not use:

"changes"
"update"
"stuff"
"final"
"done"

as commit messages.

Keep commits logically grouped.

============================================================
30. BEFORE COMMIT
============================================================

Run:

git status

Inspect:

git diff

and:

git diff --cached

Verify:

- no secrets
- no .env
- no generated junk
- no debug files
- no unrelated changes
- no temporary files
- no credentials
- no accidental large files

Check:

git status --short

============================================================
31. COMMIT
============================================================

Only commit after all applicable quality gates pass.

Commit message must explain the change.

Example:

git commit -m "feat: implement Spectora template importer"

============================================================
32. PUSH
============================================================

Push ONLY the current feature branch.

Example:

git push -u origin feature/spectora-importer

Never push feature work directly to main.

After push, verify:

git status

and:

git log -1 --oneline

Report the remote branch name.

============================================================
33. PULL REQUEST READINESS
============================================================

After pushing, report:

Branch:
Commit:
Remote:
Files changed:
Tests:
Coverage:
Ruff:
Format:
Typecheck:
Schemathesis:
Build:
Database validation:
Known limitations:

Also provide a concise PR description:

What changed
Why
How tested
Known limitations

Do not create a PR automatically unless explicitly requested.

============================================================
34. FEATURE COMPLETION DEFINITION
============================================================

A feature is NOT complete merely because the code works locally.

A feature is complete when:

1. Correct branch exists.
2. Implementation matches design.
3. API contract is respected.
4. Tests exist.
5. Tests pass.
6. Coverage is acceptable.
7. Ruff passes.
8. Formatting passes.
9. Type checks pass if configured.
10. Schemathesis passes for API features.
11. Database validation passes where possible.
12. No secrets/unrelated files exist.
13. Commit is meaningful.
14. Feature branch is pushed.
15. Remaining limitations are documented.

============================================================
35. DOCUMENTATION UPDATES
============================================================

If implementation changes behavior that is documented:

update the relevant documentation.

Possible documents:

docs/DATABASE_DESIGN.md
docs/BACKEND_DESIGN.md
docs/API-CONTRACTS.md
docs/FRONTEND_DESIGN.md
README.md
NOTES.md

Do not allow documentation to become stale.

However:

Do NOT rewrite documentation unnecessarily for implementation details that do not change the documented architecture/contract.

============================================================
36. ASSIGNMENT SCOPE CONTROL
============================================================

Always compare implementation against the original assignment.

The project exists to satisfy the assignment.

Do not add features merely because they would be useful in a commercial product.

Out-of-scope areas include:

- actual inspection reports
- scheduling
- payments
- homeowner-facing portal
- unnecessary CRM
- unnecessary analytics
- unnecessary AI

If a requested task appears outside scope:

report it before implementing.

============================================================
37. TASK EXECUTION PROTOCOL
============================================================

When the user provides a task such as:

"Implement feature: Spectora importer"

execute the following automatically:

PHASE A — UNDERSTAND

1. Inspect repository.
2. Read relevant design docs.
3. Inspect existing code.
4. Identify dependencies.
5. Define implementation plan.

PHASE B — BRANCH

6. Update main.
7. Create appropriate feature branch.

PHASE C — IMPLEMENT

8. Implement the feature.
9. Add/update tests.
10. Update required documentation.

PHASE D — VALIDATE

11. Run tests.
12. Run coverage.
13. Run Ruff.
14. Run formatting checks.
15. Run type checks if configured.
16. Run Schemathesis for API features.
17. Run database checks where applicable.
18. Run frontend lint/build/tests where applicable.

PHASE E — FIX

19. Fix all failures.
20. Rerun failed checks.
21. Repeat until quality gates pass or a genuine environmental blocker remains.

PHASE F — REVIEW

22. Inspect git diff.
23. Check for secrets.
24. Check for unrelated changes.
25. Verify assignment scope.

PHASE G — COMMIT

26. Create meaningful commit(s).

PHASE H — PUSH

27. Push feature branch.

PHASE I — REPORT

28. Provide final implementation report.

Do not ask the user to repeat these instructions.

============================================================
38. WHEN USER SAYS "CONTINUE"
============================================================

If the user says:

"continue"

or:

"next"

inspect the current repository state and determine the next logical implementation step based on:

- completed work
- branch state
- assignment
- design documents
- API contracts
- dependencies

Do not randomly start a new feature.

If multiple next steps are possible, choose the one that is explicitly next in the documented implementation sequence.

============================================================
39. WHEN USER SAYS "FIX"
============================================================

If the user says:

"fix the errors"

first inspect:

- git status
- failing test output
- lint output
- coverage output
- Schemathesis output
- application logs

Fix the root cause.

Do not weaken tests or disable quality gates merely to obtain a passing build.

============================================================
40. WHEN USER SAYS "IMPLEMENT FEATURE: X"
============================================================

Interpret this as an instruction to execute the complete implementation protocol.

Do NOT ask the user to provide the engineering workflow again.

Use:

X

as the feature scope.

Before implementation verify that X exists in:

- assignment
- design docs
- API contracts

or is a necessary implementation detail of an already approved feature.

If X is not justified:

report the scope issue.

============================================================
41. FINAL REPORT FORMAT
============================================================

Every completed task must end with:

## Implementation Summary

Feature:
Branch:
Commit:
Remote branch:

## Changes

- ...

## Tests

- pytest:
- coverage:
- ruff:
- formatting:
- typecheck:
- Schemathesis:
- database validation:
- frontend lint:
- frontend build:

Only report checks that were actually run.

## Validation

- ...

## Documentation

- ...

## Known Limitations

- ...

## Next Logical Step

- ...

Never claim a check passed unless it actually passed.