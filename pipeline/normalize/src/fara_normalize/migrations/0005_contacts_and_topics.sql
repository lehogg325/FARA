-- Phase 2: reportable-contact network graph + topic classification (docs/phase2.md).
-- extraction_runs.stage's CHECK constraint (0002) only allowed the original four
-- pipeline stages — widen it for the two new ones added here.
ALTER TABLE extraction_runs DROP CONSTRAINT extraction_runs_stage_check;
ALTER TABLE extraction_runs ADD CONSTRAINT extraction_runs_stage_check
    CHECK (stage IN ('download', 'text', 'fields_rule', 'fields_llm', 'contacts', 'topics'));

-- Dedicated tables, not EAV — both are stable multi-column shapes (same reasoning as
-- document_text/registrant_docs being real tables while document_extracted_fields
-- stays EAV for genuinely open-ended single values).

-- Item 11 "Date / Contact Method / Purpose" table — confirmed live (docs/phase2.md):
-- present in 2,025 real 2025-2026 Exhibit AB / Supplemental Statement documents, with
-- genuinely populated data in 89 of them. Contact identity is intentionally raw and
-- unresolved (contact_name_raw), same philosophy as foreign_principals.foreign_principal_name.
CREATE TABLE reportable_contacts (
    reportable_contact_id  bigserial PRIMARY KEY,
    registrant_doc_id        bigint NOT NULL REFERENCES registrant_docs(registrant_doc_id),
    contact_date               date,
    contact_date_raw             text,
    contact_name_raw              text NOT NULL,
    contact_method                 text,
    purpose                          text,
    extraction_method                 text NOT NULL CHECK (extraction_method IN ('llm')),
    extractor_version                  text NOT NULL,
    extracted_at                        timestamptz NOT NULL,
    UNIQUE (registrant_doc_id, contact_name_raw, contact_date_raw, purpose, extractor_version)
);
CREATE INDEX ix_reportable_contacts_doc ON reportable_contacts (registrant_doc_id);
CREATE INDEX ix_reportable_contacts_name_trgm ON reportable_contacts USING gin (contact_name_raw gin_trgm_ops);

-- Fixed taxonomy (docs/phase2.md) — finalized against a real random sample of
-- extracted nature_of_activities text, not guessed. sort_order controls display order
-- (substantive categories first, general_representation/other last as catch-alls).
CREATE TABLE topics (
    topic         text PRIMARY KEY,
    topic_label    text NOT NULL,
    sort_order      integer NOT NULL
);

CREATE TABLE document_topics (
    document_topic_id  bigserial PRIMARY KEY,
    registrant_doc_id    bigint NOT NULL REFERENCES registrant_docs(registrant_doc_id),
    topic                  text NOT NULL REFERENCES topics(topic),
    extractor_version       text NOT NULL,
    extracted_at              timestamptz NOT NULL,
    UNIQUE (registrant_doc_id, topic, extractor_version)
);
CREATE INDEX ix_document_topics_doc ON document_topics (registrant_doc_id);
CREATE INDEX ix_document_topics_topic ON document_topics (topic);
