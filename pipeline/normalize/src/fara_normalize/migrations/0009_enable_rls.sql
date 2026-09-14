-- Every public-schema table had Row Level Security disabled (Supabase's
-- security advisor flags this correctly): Supabase auto-provisions a REST
-- API (PostgREST) backed by the `anon`/`authenticated` roles for every
-- project regardless of whether the app uses it -- this codebase never does
-- (no supabase-js, no anon key anywhere; the backend and pipelines connect
-- directly via DATABASE_URL as the `postgres` role, which has BYPASSRLS and
-- is therefore completely unaffected by anything in this migration). Without
-- RLS, anon/authenticated had Supabase's default full read/write/delete
-- access to every row of every table over that unused REST API.
--
-- FARA's actual data (DOJ FARA filings) is meant to be public -- add a
-- public SELECT-only policy on every user-facing table, so read access
-- stays exactly as intended. No INSERT/UPDATE/DELETE policy is added
-- anywhere: there is no legitimate public write path, so the default-deny
-- (RLS enabled, no write policy) is correct everywhere.
--
-- Internal pipeline tables (bulk-load staging tables, run bookkeeping,
-- the migration ledger) get RLS enabled with no policy at all -- anon/
-- authenticated get zero access, not even read; there's no public-facing
-- reason to expose pipeline internals.
--
-- ENABLE ROW LEVEL SECURITY (without FORCE, which nothing here sets) never
-- restricts the table owner or a superuser/BYPASSRLS role, so this is safe
-- to run against local/CI Postgres (table owner) exactly as against
-- Supabase (postgres role has BYPASSRLS there). The anon/authenticated
-- roles themselves only exist on Supabase, though, so the policy-creation
-- half is wrapped in a role-existence check to stay a no-op everywhere else.

ALTER TABLE registrants ENABLE ROW LEVEL SECURITY;
ALTER TABLE foreign_principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE registrant_docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE short_form_registrants ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_text ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_extracted_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE reportable_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE countries ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE jurisdictions ENABLE ROW LEVEL SECURITY;

-- Internal-only: RLS enabled, deliberately no policy (default-deny for anon/authenticated).
ALTER TABLE stg_registrants ENABLE ROW LEVEL SECURITY;
ALTER TABLE stg_foreign_principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE stg_registrant_docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stg_short_form_registrants ENABLE ROW LEVEL SECURITY;
ALTER TABLE load_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    t text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        FOREACH t IN ARRAY ARRAY[
            'registrants', 'foreign_principals', 'registrant_docs', 'short_form_registrants',
            'document_text', 'document_extracted_fields', 'reportable_contacts', 'document_topics',
            'countries', 'document_types', 'topics', 'jurisdictions'
        ]
        LOOP
            EXECUTE format(
                'CREATE POLICY "Public read access" ON %I FOR SELECT TO anon, authenticated USING (true)', t
            );
        END LOOP;
    END IF;
END $$;
