-- routers/foreign_principals.py's default (group_by_name=True) listing path
-- always filters on jurisdiction and GROUP BYs on the same two normalized
-- expressions text_normalize.NORM_SQL produces for foreign_principal_name and
-- coalesce(country_raw, '') -- no existing index covers those expressions
-- (0007's ix_fp_jurisdiction_country is on the raw columns, and 0001's trigram
-- index is on the raw, un-normalized name), so every request to this public,
-- unauthenticated, default-mode endpoint runs an unindexed aggregation over
-- the whole table. foreign_principals is small today (17,746 rows) but this is
-- the single busiest query shape in the app and the one place a repeat visitor
-- (or a bot) can cheaply generate real load against the one shared Postgres
-- instance behind every endpoint.
CREATE INDEX ix_fp_grouped_lookup ON foreign_principals (
    jurisdiction,
    (lower(regexp_replace(trim(foreign_principal_name), '\s+', ' ', 'g'))),
    (lower(regexp_replace(trim(coalesce(country_raw, '')), '\s+', ' ', 'g')))
);
