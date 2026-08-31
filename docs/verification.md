# Pinned verification facts

Hand-verifiable assertions against `efile.fara.gov`'s live public data, checked
2026-08-23 against the loaded database (bulk snapshot date 2026-08-21).

## Registrant 6170 — Mercury Public Affairs, LLC

Registrant record: `name='Mercury Public Affairs, LLC'`, `registration_date=2013-05-14`,
`status='active'`. Confirmed against `https://efile.fara.gov/api/v1/ForeignPrincipals/html/Active/6170`
(live, unauthenticated) — every active foreign principal row returned by that endpoint
matches the loaded `foreign_principals` table exactly, field for field:

| Foreign principal | Country | Registration date | Live termination date | DB status |
|---|---|---|---|---|
| Croatian Democratic Union of Bosnia and Herzegovina | BOSNIA & HERZEGOVINA | 08/03/2026 | (none, active) | matches, active |
| Misgav Institute for National Security and Zionist Strategy | ISRAEL | 06/26/2026 | (none, active) | matches, active |
| Institut Macaya | HAITI | 06/11/2026 | (none, active) | matches, active |
| OB Projects Management Corporation CC | ZIMBABWE | 12/22/2025 | (none, active) | matches, active |
| Delvina Gas Company | ALBANIA | 10/02/2025 | (none, active) | matches, active |
| Embassy of India | INDIA | 08/18/2025 | (none, active) | matches, active |
| National Economic & Social Development Board | LIBYA | 07/21/2025 | (none, active) | matches, active |

`Yushu Technology Company, Ltd.` (CHINA, registered 2025-12-05) is correctly loaded with
`termination_date=2026-06-01` and does **not** appear in the live Active list — confirms
the status split is being applied correctly, not just the raw data.

Document counts for this registrant (981 Informational Materials, 457 Short-Form, 223
Amendment, 137 Exhibit AB, 26 Supplemental Statement, 1 Registration Statement) and 5 most
recent short-form individuals (Cortese Jr./William, Field/Anja, Thomas/Kevin, Bloom/Eric,
Ribenboim/Bernardo) were cross-checked for internal consistency against the sample PDFs
pulled during build step 1 (`pipeline/extract/tests/fixtures/pdfs/era3-*.pdf`, all filed
under reg 6170) — the Registration Statement, Amendment, Exhibit AB, and Short-Form PDFs
sampled there correspond to real rows in this registrant's `registrant_docs` records.

## Registrant 5769 — O'Malley, Sheila (data-quality regression pin)

Real bulk snapshot `2026-08-21` contains two rows for this registration number, differing
only in `Termination Date` (`08/01/2008` vs. `09/19/2006`). Loaded value after
deduplication (last row in file wins): `termination_date=2006-09-19`. If this ever loads
as `2008-08-01` instead, the loader's intra-file dedup logic has regressed — see
`docs/api-notes.md` and `pipeline/normalize/tests/test_load_registrants.py::test_intra_file_duplicate_registration_number_settles_on_last_row`.
