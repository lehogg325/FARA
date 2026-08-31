-- /api/search covers short-form individuals too (backend plan, API layer),
-- but 0001 only added trigram indexes for registrants.name and
-- foreign_principals.foreign_principal_name — this closes that gap so an
-- ILIKE '%...%' typeahead against 44K+ short-form rows stays index-backed
-- instead of falling back to a sequential scan.
CREATE INDEX ix_short_form_last_name_trgm ON short_form_registrants USING gin (last_name gin_trgm_ops);
CREATE INDEX ix_short_form_first_name_trgm ON short_form_registrants USING gin (first_name gin_trgm_ops);
