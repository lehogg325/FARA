-- Confirmed live (docs/api-notes.md): a per-row SELECT-then-INSERT/UPDATE loop
-- over registrant_docs (~150K rows) didn't finish in 8+ minutes — ~300K
-- synchronous round trips is too slow even though every query used its index.
-- registrant_docs uses a bulk COPY-into-staging + set-based INSERT/UPDATE
-- instead. Correction (0006, 2026-09-02): the original assumption below that
-- registrants/foreign_principals/short_forms could stay row-by-row held only
-- against local Postgres's near-zero round-trip latency — against a real
-- remote pooled connection (Supabase) the same round-trip-count bottleneck
-- hit those three too, just at a smaller row count. All four loaders now use
-- this same staging-table pattern; see 0006 for their staging tables.
CREATE UNLOGGED TABLE stg_registrant_docs (
    jurisdiction                    text,
    registrant_id                    bigint,
    registration_number              integer,
    date_stamped                      date,
    date_stamped_raw                  text,
    document_type_code                text,
    document_type_raw_label           text,
    short_form_name                   text,
    foreign_principal_name            text,
    foreign_principal_country_raw     text,
    url                                text,
    url_available                     boolean,
    source_row_hash                   text
);
