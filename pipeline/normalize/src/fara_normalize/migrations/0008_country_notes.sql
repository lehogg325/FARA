-- Optional clarifying note shown in the country dropdown for entries that look
-- like duplicates but are genuinely different countries/eras (or the reverse —
-- confirmed the same country under a different DOJ label). Grounded in each
-- name's real registration_date range in foreign_principals, not guessed.
ALTER TABLE countries ADD COLUMN note text;

UPDATE countries SET note = v.note FROM (VALUES
    ('USSR', 'historical — dissolved 1991'),
    ('GERMAN DEMOCRATIC REPUBLIC', 'East Germany, historical (to 1990)'),
    ('GERMANY, FEDERAL REPUBLIC OF', 'formal name for Germany; predominantly used in DOJ filings through 1991'),
    ('CZECHOSLOVAKIA', 'historical — split into Czech Republic and Slovakia in 1993'),
    ('CZECHIA', 'current name for the Czech Republic'),
    ('MACEDONIA', 'renamed North Macedonia in 2019'),
    ('NORTH MACEDONIA', 'known as Macedonia before 2019'),
    ('ZAIRE', 'historical name for Congo, Democratic Republic of the (to 1997)'),
    ('CONGO, DEMOCRATIC REPUBLIC OF THE', 'not the same country as Congo, Republic of the'),
    ('CONGO, REPUBLIC OF THE', 'not the same country as Congo, Democratic Republic of the'),
    ('YEMEN, PEOPLES DEMOCRATIC REPUBLIC OF YEMEN', 'historical name for South Yemen, before 1990 unification'),
    ('SOUTHERN YEMAN', 'variant spelling seen in historical South Yemen filings'),
    ('SOMALI DEMOCRATIC REPUBLIC', 'Somalia''s official name, 1969-1991'),
    ('SOMALILAND', 'self-declared state within Somalia, not internationally recognized'),
    ('CEYLON (SRI LANKA)', 'historical name for Sri Lanka, before 1972'),
    ('PORTUGUESE TIMOR', 'historical name for Timor-Leste, before 1975 independence'),
    ('TIMOR-LESTE (EAST TIMOR)', 'same country as Timor-Leste, different DOJ label'),
    ('REPUBLIC OF SOUTH SUDAN', 'different DOJ label for South Sudan, independent since 2011'),
    ('BURMA', 'alternate name also used in DOJ filings for Myanmar'),
    ('MYANMAR (BURMA)', 'alternate name also used in DOJ filings for Burma')
) AS v(country_name, note)
WHERE countries.jurisdiction = 'fara' AND countries.country_name = v.country_name;
