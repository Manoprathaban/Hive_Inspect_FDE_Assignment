-- =============================================================================
-- 0001_create_template_schema.sql
-- Hive Inspect Template Importer — initial schema (types, tables, constraints, indexes).
--
-- Apply once, in order, to an empty database. Deterministic and repeatable on a fresh
-- database for:
--   * local PostgreSQL
--   * Supabase PostgreSQL
--   * CI (fresh postgres container)
--
-- The Supabase Auth sync trigger below is guarded by a check for the `auth` schema, so
-- this file is valid on plain PostgreSQL too. Row Level Security is the responsibility
-- of 0002_rls_policies.sql; keep authorization policy statements out of this file.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1) Enum types
-- -----------------------------------------------------------------------------

CREATE TYPE comment_type AS ENUM ('info', 'limit', 'defect');
CREATE TYPE answer_type AS ENUM ('boolean', 'checkbox', 'date', 'number', 'range', 'text');
CREATE TYPE option_type AS ENUM ('multiple_choice', 'unit_type');
CREATE TYPE issue_type AS ENUM ('SOURCE_DATA_MISSING', 'UNSUPPORTED_CONTENT', 'INVALID_SOURCE_DATA');
CREATE TYPE issue_severity AS ENUM ('info', 'warning', 'error');

-- -----------------------------------------------------------------------------
-- 2) users (identity anchor — NOT a profiles table)
-- -----------------------------------------------------------------------------

-- Id equals a Supabase Auth user id (auth.users.id); there are no credentials or
-- profile fields here. In production a row is created by the on_auth_user_created
-- trigger below (Supabase Auth sign-up -> mirror). In local development a single
-- deterministic stub user is seeded (database/seed/dev_auth.sql) that matches the
-- DevAuthProvider identity. The application never authenticates against this table.

CREATE TABLE users (
    id         uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 3) templates
-- -----------------------------------------------------------------------------

CREATE TABLE templates (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name            text NOT NULL,
    source          text NOT NULL,              -- importer brand/format, e.g. 'spectora'
    source_filename text,                       -- original uploaded/imported filename
    copied_from_id  uuid REFERENCES templates (id) ON DELETE SET NULL,  -- provenance only
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 4) sections
-- -----------------------------------------------------------------------------

CREATE TABLE sections (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id   uuid NOT NULL REFERENCES templates (id) ON DELETE CASCADE,
    name          text NOT NULL,
    display_order integer NOT NULL CHECK (display_order >= 0),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (template_id, display_order)
);

-- -----------------------------------------------------------------------------
-- 5) items
-- -----------------------------------------------------------------------------

CREATE TABLE items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id    uuid NOT NULL REFERENCES sections (id) ON DELETE CASCADE,
    name          text NOT NULL,
    display_order integer NOT NULL CHECK (display_order >= 0),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (section_id, display_order)
);

-- -----------------------------------------------------------------------------
-- 6) comments
-- -----------------------------------------------------------------------------
-- One row per comment. content is TEXT: Spectora comment text may carry markup
-- (XML-escaped in the export, decoded during import), so the column must be free-form
-- text. The template is NEVER stored as one opaque HTML/JSON blob. Fields map to the
-- Spectora HTML-text export columns (see docs/DATABASE_DESIGN.md). source_row keeps
-- the original spreadsheet row for provenance and import-issue correlation.

CREATE TABLE comments (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id           uuid NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    name              text NOT NULL,
    content           text NOT NULL DEFAULT '',
    comment_type      comment_type NOT NULL,
    category          smallint CHECK (category IN (-1, 0, 1)),   -- Spectora: -1 Low, 0 Med, 1 High
    answer_type       answer_type NOT NULL,
    display_order     integer NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    recommendation    text,
    default_value     text,
    default_value_2   text,
    default_unit_type text,
    estimate_min      numeric(12, 2),
    estimate_max      numeric(12, 2),
    source_row        integer,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 7) comment_options
-- -----------------------------------------------------------------------------
-- Normalized child records for repeated-value columns. One table with an option_type
-- discriminator covers both "Multiple Choice Options" and "Unit Type Options" without
-- separate tables. display_order preserves the source (comma-separated) order.

CREATE TABLE comment_options (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id    uuid NOT NULL REFERENCES comments (id) ON DELETE CASCADE,
    option_type   option_type NOT NULL,
    value         text NOT NULL,
    display_order integer NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    UNIQUE (comment_id, option_type, display_order)
);

-- -----------------------------------------------------------------------------
-- 8) import_issues
-- -----------------------------------------------------------------------------
-- Persistent, user-visible record of content that was missing, unsupported, or invalid
-- during import. NOT a general logging table. issue_type distinguishes:
--   SOURCE_DATA_MISSING  -> information was not present in the export
--   UNSUPPORTED_CONTENT  -> information existed but could not be fully represented
--   INVALID_SOURCE_DATA  -> malformed source data (optional third category)

CREATE TABLE import_issues (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id  uuid NOT NULL REFERENCES templates (id) ON DELETE CASCADE,
    source_row   integer,
    source_field text,
    issue_type   issue_type NOT NULL,
    message      text NOT NULL,
    raw_value    text,
    severity     issue_severity NOT NULL DEFAULT 'warning',
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 9) updated_at maintenance
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER templates_set_updated_at
    BEFORE UPDATE ON templates FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER sections_set_updated_at
    BEFORE UPDATE ON sections FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER items_set_updated_at
    BEFORE UPDATE ON items FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER comments_set_updated_at
    BEFORE UPDATE ON comments FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -----------------------------------------------------------------------------
-- 10) Indexes
-- -----------------------------------------------------------------------------
-- Only useful indexes. sections (template_id, display_order), items (section_id,
-- display_order), and comment_options (comment_id, option_type, display_order) are
-- already covered by their UNIQUE constraints. See docs/DATABASE_DESIGN.md for the
-- rationale of each one.

CREATE INDEX templates_owner_id_idx ON templates (owner_id);
CREATE INDEX comments_item_order_idx ON comments (item_id, display_order);
CREATE INDEX import_issues_template_id_idx ON import_issues (template_id);

-- -----------------------------------------------------------------------------
-- 11) Supabase Auth integration (guarded — applies only when `auth` schema exists)
-- -----------------------------------------------------------------------------

-- Mirrors a newly created Supabase Auth user into public.users so FK integrity holds.
CREATE OR REPLACE FUNCTION handle_new_user() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.users (id) VALUES (NEW.id) ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DO $auth$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
        CREATE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION handle_new_user();
    END IF;
END
$auth$;

COMMIT;