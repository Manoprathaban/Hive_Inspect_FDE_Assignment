-- =============================================================================
-- 0002_rls_policies.sql
-- Hive Inspect Template Importer — Row Level Security policies.
--
-- Applies AFTER 0001_create_template_schema.sql. On Supabase (where the `auth` schema
-- exists) every user-owned table gets RLS enabled and per-table policies keyed on the
-- authenticated Supabase user (auth.uid()). On plain local PostgreSQL / CI the `auth`
-- schema does not exist, so this block is a no-op and the application layer is the
-- ownership enforcement point (see docs/DATABASE_DESIGN.md).
--
-- Strategy: normalized ownership. owner_id lives ONLY on templates; child tables prove
-- ownership by walking their parent chain to the template owner (EXISTS subqueries).
-- RLS is never disabled for the development stub: locally the backend uses a privileged
-- connection and enforces the same owner_id scoping in the application layer.
-- =============================================================================

BEGIN;

DO $rls$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN

        -- users: a user sees/updates only their own identity row.
        ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY users_self ON public.users
                 USING (id = auth.uid())
                 WITH CHECK (id = auth.uid())';

        -- templates: ownership boundary starts here.
        ALTER TABLE public.templates ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY templates_owner_all ON public.templates
                 USING (owner_id = auth.uid())
                 WITH CHECK (owner_id = auth.uid())';

        -- Every child table uses the same normalized pattern: the WITH CHECK clause
        -- prevents attaching a child row under a template/owner the user does not own;
        -- USING prevents reading/updating/deleting another user's rows.

        ALTER TABLE public.sections ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY sections_owner_all ON public.sections
                 USING (EXISTS (SELECT 1 FROM public.templates t WHERE t.id = sections.template_id AND t.owner_id = auth.uid()))
                 WITH CHECK (EXISTS (SELECT 1 FROM public.templates t WHERE t.id = sections.template_id AND t.owner_id = auth.uid()))';

        ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY items_owner_all ON public.items
                 USING (EXISTS (SELECT 1 FROM public.sections s JOIN public.templates t ON t.id = s.template_id WHERE s.id = items.section_id AND t.owner_id = auth.uid()))
                 WITH CHECK (EXISTS (SELECT 1 FROM public.sections s JOIN public.templates t ON t.id = s.template_id WHERE s.id = items.section_id AND t.owner_id = auth.uid()))';

        ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY comments_owner_all ON public.comments
                 USING (EXISTS (SELECT 1 FROM public.items i JOIN public.sections s ON s.id = i.section_id JOIN public.templates t ON t.id = s.template_id WHERE i.id = comments.item_id AND t.owner_id = auth.uid()))
                 WITH CHECK (EXISTS (SELECT 1 FROM public.items i JOIN public.sections s ON s.id = i.section_id JOIN public.templates t ON t.id = s.template_id WHERE i.id = comments.item_id AND t.owner_id = auth.uid()))';

        ALTER TABLE public.comment_options ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY comment_options_owner_all ON public.comment_options
                 USING (EXISTS (SELECT 1 FROM public.comments c JOIN public.items i ON i.id = c.item_id JOIN public.sections s ON s.id = i.section_id JOIN public.templates t ON t.id = s.template_id WHERE c.id = comment_options.comment_id AND t.owner_id = auth.uid()))
                 WITH CHECK (EXISTS (SELECT 1 FROM public.comments c JOIN public.items i ON i.id = c.item_id JOIN public.sections s ON s.id = i.section_id JOIN public.templates t ON t.id = s.template_id WHERE c.id = comment_options.comment_id AND t.owner_id = auth.uid()))';

        ALTER TABLE public.import_issues ENABLE ROW LEVEL SECURITY;
        EXECUTE 'CREATE POLICY import_issues_owner_all ON public.import_issues
                 USING (EXISTS (SELECT 1 FROM public.templates t WHERE t.id = import_issues.template_id AND t.owner_id = auth.uid()))
                 WITH CHECK (EXISTS (SELECT 1 FROM public.templates t WHERE t.id = import_issues.template_id AND t.owner_id = auth.uid()))';

    END IF;
END
$rls$;

COMMIT;