-- Metadata layer, sourced from the 4 daily bulk CSVs (docs/api-notes.md).
-- No amendment-lane resolution here (unlike LDA): a FARA Registration Number is
-- one durable identity for a registrant's whole life, so registrants/short_form_registrants/
-- foreign_principals are plain type-1 slowly-changing dimensions (upsert-in-place).
-- registrant_docs is the one append-only, event-sourced table.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE jurisdictions (
    jurisdiction   text PRIMARY KEY,
    display_name   text NOT NULL,
    level          text NOT NULL CHECK (level IN ('federal', 'state')),
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Free text, NOT a coded dimension (correction vs. initial design — docs/api-notes.md):
-- the bulk CSVs carry country/location as plain strings, including confirmed historical
-- variants (GREAT BRITAIN / UNITED KINGDOM) and real data-quality anomalies. No FK
-- enforcement from foreign_principals/registrant_docs — this table is seeded once from
-- observed values and auto-grows; it exists only to back /api/countries and UI filters.
CREATE TABLE countries (
    jurisdiction   text NOT NULL REFERENCES jurisdictions(jurisdiction),
    country_name   text NOT NULL,
    PRIMARY KEY (jurisdiction, country_name)
);

-- Confirmed closed, complete 10-value vocabulary (docs/api-notes.md) — FK-enforced
-- with fail-loud reconciliation on load, unlike countries.
CREATE TABLE document_types (
    jurisdiction           text NOT NULL REFERENCES jurisdictions(jurisdiction),
    document_type_code     text NOT NULL,
    document_type_label    text NOT NULL,
    PRIMARY KEY (jurisdiction, document_type_code)
);
CREATE UNIQUE INDEX ux_document_types_label ON document_types (jurisdiction, document_type_label);

CREATE TABLE registrants (
    registrant_id               bigserial PRIMARY KEY,
    jurisdiction                 text NOT NULL REFERENCES jurisdictions(jurisdiction),
    registration_number          integer NOT NULL,
    name                          text NOT NULL,
    business_name                 text,
    address_1                     text,
    address_2                     text,
    city                          text,
    state                         text,
    zip                           text,
    registration_date             date,
    termination_date              date,
    status                        text NOT NULL CHECK (status IN ('active', 'terminated')),
    source_row_hash               text NOT NULL,
    first_seen_snapshot_date      date NOT NULL,
    last_seen_snapshot_date       date NOT NULL,
    updated_at                    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jurisdiction, registration_number)
);
CREATE INDEX ix_registrants_name_trgm ON registrants USING gin (name gin_trgm_ops);
CREATE INDEX ix_registrants_status ON registrants (jurisdiction, status);

CREATE TABLE short_form_registrants (
    short_form_registrant_id     bigserial PRIMARY KEY,
    jurisdiction                  text NOT NULL REFERENCES jurisdictions(jurisdiction),
    parent_registrant_id          bigint NOT NULL REFERENCES registrants(registrant_id),
    parent_registration_number    integer NOT NULL,
    -- Nullable: confirmed live, 9 of 44,606 rows have a genuinely blank Short
    -- Form Last Name in the source (docs/api-notes.md) — not corruption, a
    -- real gap in some historical and a few current filings.
    last_name                     text,
    first_name                    text,
    short_form_date               date,
    termination_date              date,
    source_row_hash               text NOT NULL,
    first_seen_snapshot_date      date NOT NULL,
    last_seen_snapshot_date       date NOT NULL,
    updated_at                    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jurisdiction, parent_registration_number, last_name, first_name, short_form_date)
);
CREATE INDEX ix_short_form_parent ON short_form_registrants (parent_registrant_id);

CREATE TABLE foreign_principals (
    foreign_principal_id       bigserial PRIMARY KEY,
    jurisdiction                 text NOT NULL REFERENCES jurisdictions(jurisdiction),
    registrant_id                bigint NOT NULL REFERENCES registrants(registrant_id),
    registration_number          integer NOT NULL,
    foreign_principal_name       text NOT NULL,
    country_raw                  text,
    address_1                    text,
    address_2                    text,
    city                         text,
    state                        text,
    zip                          text,
    registration_date            date,
    termination_date             date,
    source_row_hash              text NOT NULL,
    first_seen_snapshot_date     date NOT NULL,
    last_seen_snapshot_date      date NOT NULL,
    updated_at                   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jurisdiction, registration_number, foreign_principal_name, country_raw, registration_date)
);
CREATE INDEX ix_fp_registrant ON foreign_principals (registrant_id);
CREATE INDEX ix_fp_name_trgm ON foreign_principals USING gin (foreign_principal_name gin_trgm_ops);

-- The one genuinely append-only, event-sourced table: one row per filed document.
-- PDF-archive provenance columns are added by 0002 once the document-mining layer exists,
-- to keep this migration scoped to what's sourced directly from the bulk CSV.
CREATE TABLE registrant_docs (
    registrant_doc_id             bigserial PRIMARY KEY,
    jurisdiction                   text NOT NULL REFERENCES jurisdictions(jurisdiction),
    registrant_id                  bigint NOT NULL REFERENCES registrants(registrant_id),
    registration_number            integer NOT NULL,
    date_stamped                   date,  -- nullable: one malformed value confirmed live (docs/api-notes.md) — log, don't crash
    date_stamped_raw               text NOT NULL,
    document_type_code             text,
    document_type_raw_label        text NOT NULL,
    short_form_name                text,
    foreign_principal_name         text,
    foreign_principal_country_raw  text,
    url                            text,
    url_available                  boolean NOT NULL,
    source_row_hash                text NOT NULL,
    first_seen_snapshot_date       date NOT NULL,
    last_seen_snapshot_date        date NOT NULL,
    updated_at                     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (jurisdiction, document_type_code) REFERENCES document_types(jurisdiction, document_type_code)
);
-- Confirmed live: URL alone doesn't disambiguate distinct documents when it's the
-- 'Available-FARA-Public-Office' sentinel — many office-only Short-Form filings from
-- different individuals under one registrant share a date, so short_form_name and
-- foreign_principal_name must be part of the key too (docs/api-notes.md). Nullable
-- columns require the whole index to tolerate NULLs distinguishing rows, which Postgres
-- unique indexes already do correctly (NULLs are never considered equal to each other).
CREATE UNIQUE INDEX ux_registrant_docs_natural_key
    ON registrant_docs (jurisdiction, registration_number, document_type_raw_label, date_stamped_raw, url, short_form_name, foreign_principal_name);
CREATE INDEX ix_registrant_docs_registrant ON registrant_docs (registrant_id);
CREATE INDEX ix_registrant_docs_date ON registrant_docs (jurisdiction, date_stamped);

-- Provenance / load tracking — LDA's load_state equivalent.
CREATE TABLE load_runs (
    load_run_id            bigserial PRIMARY KEY,
    jurisdiction             text NOT NULL REFERENCES jurisdictions(jurisdiction),
    dataset                  text NOT NULL,
    snapshot_date            date NOT NULL,
    source_archive_key       text NOT NULL,
    source_row_count         integer NOT NULL,
    loaded_row_count         integer NOT NULL,
    unmapped_row_count       integer NOT NULL DEFAULT 0,
    started_at               timestamptz NOT NULL,
    finished_at              timestamptz,
    status                   text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    error_message            text,
    UNIQUE (jurisdiction, dataset, snapshot_date)
);
