-- =============================================================================
-- dev_auth.sql — development-only identity seed.
--
-- Seeds ONLY the demo identity that DEV_AUTH_USERS maps `demo@hive.test` onto
-- (backend/app/adapters/authentication/dev.py). The dev provider derives a stable
-- per-credential id for any other email and creates its public.users row on first request,
-- so those tenants need no seed here.
--
-- WARNING: development/testing only. Never apply this seed to a production
-- Supabase database. In production, public.users rows are created automatically
-- by the on_auth_user_created trigger (see 0001_create_template_schema.sql).
-- =============================================================================

INSERT INTO public.users (id)
VALUES ('00000000-0000-0000-0000-000000000001')
ON CONFLICT (id) DO NOTHING;