-- foreign_principals.country_raw had no index at all — every country-detail-page
-- endpoint (graph.py, countries.py, documents.py) filters on
-- (jurisdiction, country_raw) and had to scan the whole table via a different
-- index (ix_fp_registrant) plus a Filter clause instead.
CREATE INDEX ix_fp_jurisdiction_country ON foreign_principals (jurisdiction, country_raw);
