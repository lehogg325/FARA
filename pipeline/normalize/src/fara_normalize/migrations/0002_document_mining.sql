-- Document-mining layer: PDF archive provenance + extracted text/fields (docs/extraction.md).
-- fara-extract (pipeline/extract, not yet built) populates these; registrant_docs itself
-- comes entirely from 0001 / the bulk CSV loader.

-- Whether this row even has a URL worth trying lives on `url_available` (0001,
-- set at metadata-load time straight from the CSV — no fetch needed to know it).
-- These columns are strictly about what fara-extract's download attempt did.
ALTER TABLE registrant_docs ADD COLUMN pdf_object_key   text;
ALTER TABLE registrant_docs ADD COLUMN pdf_sha256        text;
ALTER TABLE registrant_docs ADD COLUMN pdf_byte_size     integer;
ALTER TABLE registrant_docs ADD COLUMN pdf_http_status   integer;
ALTER TABLE registrant_docs ADD COLUMN pdf_downloaded_at timestamptz;

CREATE TABLE document_text (
    registrant_doc_id     bigint PRIMARY KEY REFERENCES registrant_docs(registrant_doc_id),
    extracted_text          text NOT NULL,
    extraction_method       text NOT NULL CHECK (extraction_method IN ('native', 'ocr', 'mixed')),
    page_count               integer,
    char_count                integer,
    quality_flag              text NOT NULL CHECK (quality_flag IN ('ok', 'low_confidence', 'failed')),
    extractor_version         text NOT NULL,
    extracted_at              timestamptz NOT NULL,
    text_search               tsvector GENERATED ALWAYS AS (to_tsvector('english', extracted_text)) STORED
);
CREATE INDEX ix_document_text_search ON document_text USING gin (text_search);

CREATE TABLE document_extracted_fields (
    document_extracted_field_id  bigserial PRIMARY KEY,
    registrant_doc_id              bigint NOT NULL REFERENCES registrant_docs(registrant_doc_id),
    field_key                       text NOT NULL,
    field_value_text                 text,
    field_value_numeric               numeric,
    field_value_date                  date,
    source_page                       integer,
    extraction_method                 text NOT NULL CHECK (extraction_method IN ('rule', 'llm')),
    extractor_version                  text NOT NULL,
    confidence                         numeric,
    extracted_at                       timestamptz NOT NULL,
    UNIQUE (registrant_doc_id, field_key, extractor_version)
);
CREATE INDEX ix_extracted_fields_doc ON document_extracted_fields (registrant_doc_id);
CREATE INDEX ix_extracted_fields_key ON document_extracted_fields (field_key);

CREATE TABLE extraction_runs (
    extraction_run_id    bigserial PRIMARY KEY,
    registrant_doc_id      bigint NOT NULL REFERENCES registrant_docs(registrant_doc_id),
    stage                    text NOT NULL CHECK (stage IN ('download', 'text', 'fields_rule', 'fields_llm')),
    extractor_version         text NOT NULL,
    status                    text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'skipped')),
    started_at                timestamptz NOT NULL,
    finished_at               timestamptz,
    error_message             text,
    UNIQUE (registrant_doc_id, stage, extractor_version)
);
