-- Defense-in-depth for the credential-leak incident (docs/deploy.md): the app
-- has always connected as `postgres`, a role with BYPASSRLS -- so 0009's RLS
-- policies protect nothing for the connection actually used, and a leaked
-- credential was (and, until this migration's role is actually adopted, still
-- is) a leaked superuser-equivalent. This creates a NOLOGIN role holding
-- exactly the grants the app needs, plus its own RLS policies, separate from
-- 0009's anon/authenticated ones (those exist for Supabase's unused
-- auto-provisioned PostgREST API; this role is for this app's own
-- connection, a different concept even though most of the grants happen to
-- be identical).
--
-- Table list is every table any router in backend/src/fara_backend actually
-- reads (confirmed by grepping every FROM/JOIN across routers/ and graph.py)
-- -- NOT simply 0009's "public-facing" list. Those differ by one thing:
-- meta.py's /api/meta aggregates over load_runs/extraction_runs (dataset
-- freshness, extraction coverage) even though 0009 correctly keeps those two
-- off the public PostgREST surface as internal pipeline bookkeeping -- a
-- real gap caught by testing this role's connection against every router
-- before adopting it live (it 500'd on /api/meta with "permission denied for
-- table load_runs" until these were added here). Confirmed via grep there is
-- no INSERT/UPDATE/DELETE endpoint anywhere, so SELECT-only is sufficient.
--
-- No password is set here (or anywhere in git) -- LOGIN and a password are
-- granted separately, directly against each environment that needs this role
-- to actually connect as it, the same way the one time this mattered (the
-- incident) was handled: never in a file that gets committed.
--
-- NOLOGIN roles and CREATE POLICY both work identically against local/CI
-- Postgres (table owner) and Supabase (postgres role has BYPASSRLS there) --
-- this migration is a harmless no-op locally beyond creating an unused role,
-- since local dev/CI keep connecting as their own owner role.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fara_app') THEN
        CREATE ROLE fara_app NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO fara_app;
GRANT SELECT ON
    registrants, foreign_principals, registrant_docs, short_form_registrants,
    document_text, document_extracted_fields, reportable_contacts, document_topics,
    countries, document_types, topics, jurisdictions, load_runs, extraction_runs
TO fara_app;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'registrants', 'foreign_principals', 'registrant_docs', 'short_form_registrants',
        'document_text', 'document_extracted_fields', 'reportable_contacts', 'document_topics',
        'countries', 'document_types', 'topics', 'jurisdictions', 'load_runs', 'extraction_runs'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE tablename = t AND policyname = 'fara_app read access'
        ) THEN
            EXECUTE format(
                'CREATE POLICY "fara_app read access" ON %I FOR SELECT TO fara_app USING (true)', t
            );
        END IF;
    END LOOP;
END $$;
