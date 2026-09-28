-- =============================================================================
-- dev_auth.sql — development-only identity seed.
--
-- Complements the backend DevAuthProvider (app/adapters/authentication/dev.py),
-- which resolves requests to this same deterministic user id.
--
-- WARNING: development/testing only. Never apply this seed to a production
-- Supabase database. In production, public.users rows are created automatically
-- by the on_auth_user_created trigger (see 0001_create_template_schema.sql).
-- =============================================================================

INSERT INTO public.users (id)
VALUES ('00000000-0000-0000-0000-000000000001')
ON CONFLICT (id) DO NOTHING;