# Phase 2 — Country Search, Reportable-Contact Graph, Topic Breakdown

Real findings and decisions from building country search, the "reportable contact"
network graph, and topic classification. See
[the approved plan](https://github.com/lehogg325/FARA) commit history for the original
scoping; this doc tracks what changed once real data got involved.

## "Reportable contact" is a real FARA field, and it was 43%, then it was 4.4%

Item 11 of the Registration Statement/Supplemental Statement asks registrants to list
political activities in a `Date / Contact Method / Purpose` table. The first pass at
measuring how often this table is actually filled in used a loose heuristic (any date
token within 800 chars of the header) and found "894 of 2,073 documents (43%) populated."
That heuristic had a real bug: it was matching dates from the *next* question's own
contribution table, not the Item 11 table itself. A tighter anchor (stop at the next
boilerplate marker or numbered item, matching the same false-positive-bleed lesson
already learned from `fields_rules.py`'s contribution extraction) found the real number:
**89 of 2,025 documents (4.4%)** have genuine inline contact data. The rest defer to a
separate appendix or leave the table blank.

This mattered for design, not just accuracy: with only ~4% of documents worth an LLM
call, `fields_contacts.py`'s `find_populated_contact_windows()` runs a cheap rule-based
pre-filter *before* ever calling the LLM — documents where the window doesn't look
populated are recorded as `succeeded` with zero contacts, no API call made. This cut
real backfill cost by roughly the same ~96% instead of sending every candidate document.

**Row density surprised us the other direction, though.** A populated document isn't
necessarily a *small* number of rows — one real PR-campaign filing (doc 402) has 105
distinct contact rows in one table (a media-outreach campaign listing every journalist
contacted). This first showed up as a real backfill bug: `extract_reportable_contacts()`'s
`max_tokens=2048` truncated the JSON response mid-string on documents with dozens of
rows, failing validation. Fixed by raising it to 8192.

## The graph had to be scoped to contact/contribution activity, not the full roster

The first version of `build_country_graph()` included every foreign principal and
registrant for a country. For China, that's 277 foreign principals and 197 registrants
— and the vast majority have *only* a bare "represents" relationship, no contact or
contribution data at all. Against the original 500-node cap, those bulk relationship
nodes consumed the entire budget before a single `contact` or `recipient` node — the
actual point of a "reportable contact network" — could appear.

Fixed by scoping the graph to registrants that have at least one `reportable_contacts`
row or `political_contribution[i]` field — the full representation roster is already
served by `/api/registrants` and `/api/foreign-principals` from phase 1; this graph is
specifically the sparse, interesting subgraph. Real result for China: 17 registrants, 34
foreign principals, 93 named contacts, 1,225 contribution recipients, 1,632 edges, no
truncation (cap raised to 1,500 as a genuine backstop). Rendering that many nodes with
`graphology-layout-forceatlas2`'s default (non-Barnes-Hut) settings would freeze the tab
for several seconds — `barnesHutOptimize` is enabled above 200 nodes.

## Topic taxonomy

Finalized against a real random sample of 40 `nature_of_activities` extractions across
diverse countries (not guessed): 20 categories, from `trade_economic` down to a
`general_representation` catch-all for the large share of filings that only describe
*how* a registrant operates (government relations, public affairs, lobbying) without
naming a substantive policy subject. Seed values live in
`ingest/src/fara_ingest/sources/fara/seed_data/topics.csv`, loaded via
`fara_normalize.load_dimensions.load_topics()`.

## China/Taiwan/Hong Kong

Kept fully separate everywhere (search, filters, graph, country stats) per your
decision — FARA's own data already treats them as three distinct `country_raw` values,
and nothing in this build merges them.

## Real 2025-2026 backfill scale

- Contacts: 2,025 candidate documents, ~89 real LLM calls (the rest skip the API
  entirely via the rule-based pre-filter).
- Topics: 688 candidate documents, one classification call each.
