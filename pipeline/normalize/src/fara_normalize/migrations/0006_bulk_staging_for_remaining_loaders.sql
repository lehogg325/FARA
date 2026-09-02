-- Correction to 0003's assumption: "registrants/foreign_principals/short_forms
-- stay row-by-row: at 7K-45K rows they complete in well under a second" held
-- against local Postgres (near-zero round-trip latency) but not against a real
-- remote pooled connection. Confirmed live against Supabase's session pooler
-- (2026-09-02): registrants (7,079 rows) took 3m42s, foreign_principals
-- (17,745 rows) took 8m23s — ~30 rows/sec, consistent with 2 synchronous round
-- trips per row (one SELECT, one INSERT/UPDATE) at real network latency. At
-- that rate the ingest-bulk workflow's 30-minute timeout can't even finish
-- short_form_registrants, let alone all three. Same fix as registrant_docs
-- already uses (0003): a staging table + bulk COPY + 3 set-based statements.
CREATE UNLOGGED TABLE stg_registrants (
    jurisdiction               text,
    registration_number         integer,
    name                         text,
    business_name                text,
    address_1                    text,
    address_2                    text,
    city                         text,
    state                        text,
    zip                          text,
    registration_date            date,
    termination_date             date,
    status                       text,
    source_row_hash              text
);

CREATE UNLOGGED TABLE stg_foreign_principals (
    jurisdiction               text,
    registrant_id                bigint,
    registration_number          integer,
    foreign_principal_name       text,
    country_raw                  text,
    address_1                    text,
    address_2                    text,
    city                         text,
    state                        text,
    zip                          text,
    registration_date            date,
    termination_date             date,
    source_row_hash              text
);

CREATE UNLOGGED TABLE stg_short_form_registrants (
    jurisdiction               text,
    parent_registrant_id         bigint,
    parent_registration_number   integer,
    last_name                    text,
    first_name                   text,
    short_form_date              date,
    termination_date             date,
    source_row_hash              text
);
