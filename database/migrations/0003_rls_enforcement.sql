-- =============================================================================
-- 0003_rls_enforcement.sql
-- Hive Inspect Template Importer — make the 0002 RLS policies actually enforce.
--
-- 0002 created correct `auth.uid()`-keyed policies, but they never applied to the backend:
-- the application connected as `postgres`, which OWNS all seven tables, and a table owner
-- is exempt from its own row-level security (relforcerowsecurity = false). The policies were
-- therefore inert and the application layer's `owner_id` predicates were the only thing
-- standing between two users. docs/DATABASE_DESIGN.md already described RLS as an active
-- second wall, so this migration makes the database match that description instead of
-- weakening the policies.
--
-- It introduces a dedicated NON-OWNER role for the application and grants the login role
-- membership in it, so each request can drop to that role and publish the acting user's
-- claims inside its transaction:
--
--     SET LOCAL ROLE hive_app;
--     SELECT set_config('request.jwt.claims', '{"sub":"<user uuid>","role":"authenticated"}', true);
--
-- Within that transaction `current_user` is neither a superuser nor a table owner, so the
-- 0002 policies apply, and `auth.uid()` resolves from the claims the backend derives from
-- the verified UserContext — never from client input. Both statements are transaction
-- scoped (SET LOCAL / set_config(..., true)), so a pooled connection cannot carry one
-- user's identity into another user's request; the identity is discarded on COMMIT or
-- ROLLBACK. `app/infrastructure/database/__init__.py::owner_scoped_connection` performs
-- exactly this.
--
-- The role is NOLOGIN by design: it is only ever assumed with SET ROLE, so it holds no
-- password and cannot be used to open a direct connection, and NOBYPASSRLS guarantees it
-- can never be granted a way around the policies. This changes no data and no policy —
-- it only gives the existing policies a subject they can bind to.
-- =============================================================================

BEGIN;

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hive_app') THEN
        CREATE ROLE hive_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOBYPASSRLS;
    END IF;
END
$role$;

-- The application reaches only the public schema and only its own tables. There are no
-- sequences in the schema (every key is a uuid), but the grant is included so a later
-- migration adding one does not silently fail on insert.
GRANT USAGE ON SCHEMA public TO hive_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hive_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hive_app;

-- Let the role that owns this database — the login role in DATABASE_URL — assume hive_app.
-- Named dynamically so this works for both `postgres` and Supabase's
-- `postgres.<project-ref>` pooler role.
DO $membership$
BEGIN
    EXECUTE format('GRANT hive_app TO %I', current_user);
END
$membership$;

COMMIT;
