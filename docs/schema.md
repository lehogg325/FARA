# Schema conventions

The migrations in `pipeline/normalize/src/fara_normalize/migrations/` are the source of
truth; this documents decisions that aren't obvious from the DDL, and why the loaders are
built the way they are.

## No amendment-lane resolution (unlike LDA)

A FARA Registration Number is one durable identity for a registrant's whole life —
amendments are just more `registrant_docs` rows against the same number, never a value
superseding an earlier one's meaning. `registrants`, `short_form_registrants`, and
`foreign_principals` are plain type-1 slowly-changing dimensions (upsert-in-place, tracked
via `first_seen_snapshot_date`/`last_seen_snapshot_date`); `registrant_docs` is the one
genuinely append-only, event-sourced table.

## Countries are free text, never FK-enforced

Confirmed live (`docs/api-notes.md`): the bulk CSVs carry country/location as plain
strings — 282 distinct values observed, including coexisting historical spellings
(`GREAT BRITAIN` / `UNITED KINGDOM`) and real column-shift corruption (dates and a bare
number that leaked into this field from elsewhere). `countries` is seeded once from
observed clean values and auto-grows via `register_observed_country` — there is no closed
vocabulary to enforce here, unlike `document_types` (confirmed closed, 10 values, FK-enforced
with fail-loud reconciliation).

## Natural keys had to be discovered empirically, not assumed

- **`registrants`**: `(jurisdiction, registration_number)`. Confirmed live: one real
  duplicate (reg 5769) appears twice in a single snapshot with conflicting `Termination
  Date` values — every loader deduplicates by natural key before writing, last row in the
  file wins, or a loader would flip-flop between the two versions on every re-run forever.
- **`registrant_docs`**: `(jurisdiction, registration_number, document_type_raw_label,
  date_stamped_raw, url, short_form_name, foreign_principal_name)`. URL alone looked
  sufficient until real data proved otherwise: 18.1% of documents share the literal
  `Available-FARA-Public-Office` sentinel instead of a real URL, and many people's
  Short-Form filings land on the same registrant + date + sentinel — only
  `short_form_name`/`foreign_principal_name` disambiguate them. Confirmed by loading the
  real file: the naive key produced 4,932 false "duplicate" groups (18,082 rows); the
  expanded key cut that to 382 groups (821 rows), 381 of which are genuinely
  byte-identical duplicate exports.
- **`short_form_registrants.last_name`** is nullable — confirmed live, 9 of 44,606 real
  rows have a genuinely blank last name (not corruption).

## Malformed rows are a real, recurring, quantifiable failure mode

`csv_readers.is_malformed_row()` detects `csv.DictReader`'s restkey overflow (`None` key),
which fires when unescaped double quotes inside a field (e.g. `NGO "Free and Faithful"`)
shift every later column. Confirmed live in `foreign_principals`: 14 of 17,739 rows, only
9 of which also happen to leave `Registration Number` non-numeric — the other 5 still
"look" valid there while other columns are corrupted, so checking `Registration Number`
alone isn't sufficient. Every loader checks `is_malformed_row` first and skips-and-counts
rather than crashing or guessing at repair.

## Load strategy: row-by-row for three tables, bulk for one

`registrants` (7K rows), `foreign_principals` (18K), and `short_form_registrants` (45K)
load via a per-row `SELECT` (classify insert/update/unchanged) then the matching
`INSERT`/`UPDATE` — simple, directly testable, and fast enough at this scale (all three
complete in well under a second).

`registrant_docs` (150K+ rows) does not: confirmed live, the same per-row approach — about
300K synchronous round trips — didn't finish in 8+ minutes even though every query hit its
index; round-trip count itself was the bottleneck. It instead bulk-loads into an `UNLOGGED`
staging table (`stg_registrant_docs`) via `COPY`, then runs three set-based statements in a
specific order that matters:

1. `UPDATE ... WHERE source_row_hash IS DISTINCT FROM staging's hash` (existing, changed rows)
2. `UPDATE ... WHERE source_row_hash = staging's hash` (existing, unchanged rows — touches `last_seen_snapshot_date`)
3. `INSERT ... WHERE NOT EXISTS` (brand new rows)

Steps 1-2 must run **before** step 3: a freshly inserted row's hash trivially equals its
own staging row's hash, so running the insert first caused every insert to also be counted
as "unchanged" (confirmed live before reordering fixed it). Full real-file load: ~150K rows
in ~8 seconds; re-running the identical file settles to `inserted=0, updated=0,
unchanged=153164` with zero drift.

## Search indexes (0004)

`0001` added `gin_trgm_ops` indexes for `registrants.name` and
`foreign_principals.foreign_principal_name` but missed `short_form_registrants` — a gap
that only surfaced once the backend's `/api/search` typeahead (which covers all three
entity types per the plan) was actually built. `0004_search_indexes.sql` adds matching
trigram indexes on `short_form_registrants.last_name`/`first_name` so an `ILIKE '%...%'`
lookup across 44K+ rows stays index-backed instead of falling back to a sequential scan.
