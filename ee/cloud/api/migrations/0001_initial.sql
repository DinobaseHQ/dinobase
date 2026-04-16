-- Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
-- See ee/LICENSE for details.

-- Dinobase EE initial schema for Supabase Postgres.
--
-- Apply via Supabase Dashboard:
--   1. Open your project at supabase.com
--   2. Sidebar -> SQL Editor -> New query
--   3. Paste this whole file and click "Run"
--
-- Tables created (all in `public` schema):
--   - user_profiles : per-user storage URL pointing at their S3 prefix
--   - user_sources  : connected data sources with encrypted credentials
--   - sync_jobs     : sync queue + history (worker polls 'pending' rows)
--
-- All tables have RLS enabled with NO policies, which means non-service-role
-- keys cannot read or write anything. The EE backend uses the Supabase
-- service role key (which bypasses RLS) to access these tables on behalf
-- of authenticated users.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- user_profiles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_profiles (
    user_id     UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    storage_url TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- user_sources
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_sources (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id               UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_name           TEXT NOT NULL,
    source_type           TEXT NOT NULL,
    auth_method           TEXT NOT NULL,
    credentials_encrypted TEXT NOT NULL,
    sync_interval         TEXT NOT NULL DEFAULT '1h',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, source_name)
);

CREATE INDEX IF NOT EXISTS user_sources_user_id_idx
    ON public.user_sources (user_id);

-- ---------------------------------------------------------------------------
-- sync_jobs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sync_jobs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_name   TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending','running','success','error','cancelled')),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    tables_synced INTEGER NOT NULL DEFAULT 0,
    tables_total  INTEGER NOT NULL DEFAULT 0,
    rows_synced   INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sync_jobs_user_id_idx
    ON public.sync_jobs (user_id);

-- Worker polls pending jobs ordered by created_at; partial index speeds it up.
CREATE INDEX IF NOT EXISTS sync_jobs_pending_created_at_idx
    ON public.sync_jobs (created_at)
    WHERE status = 'pending';

-- For the per-user "latest job per source" lookup in get_latest_sync_jobs.
CREATE INDEX IF NOT EXISTS sync_jobs_user_id_created_at_idx
    ON public.sync_jobs (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.dinobase_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS user_profiles_set_updated_at ON public.user_profiles;
CREATE TRIGGER user_profiles_set_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.dinobase_set_updated_at();

DROP TRIGGER IF EXISTS user_sources_set_updated_at ON public.user_sources;
CREATE TRIGGER user_sources_set_updated_at
    BEFORE UPDATE ON public.user_sources
    FOR EACH ROW EXECUTE FUNCTION public.dinobase_set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
-- Enable RLS with no policies: anon and authenticated keys are denied.
-- Only the service_role key (used by the EE backend) can read/write.
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_sources  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_jobs     ENABLE ROW LEVEL SECURITY;
