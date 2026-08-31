# FARA API notes — reconnaissance findings

All findings below are verified live against `efile.fara.gov` on **2026-08-21** by direct download/curl, not taken from third-party wrappers or prior knowledge. Where a finding is inferred rather than directly observed, it's marked as such.

## Base URL and endpoints

Base: `https://efile.fara.gov/api/v1/`. No authentication required for reads.

| Endpoint | Status | Notes |
|---|---|---|
| `Registrants/json/Active` | **works** | 536 rows today |
| `Registrants/json/Terminated` | **works** | adds `Termination_Date` |
| `Registrants/json/New?from=&to=` | broken | ORDS redirects to a malformed callback URL, 404s |
| `RegDocs/json/:regNum` | broken | same failure mode, even for registrants with real data |
| `ForeignPrincipals/json\|html/...` | JSON broken, **HTML works** | HTML is a client-paginated Interactive Report — not a reliable bulk path |
| `ShortFormRegistrants/json\|html/...` | JSON broken, HTML works | same caveat |
| `DocumentTypes/json` | broken; `DocumentTypes/html` **works** | confirmed the 10-code list (below) |
| `Countries/json` | broken; `Countries/html` works | paginated, not a practical bulk source — see Country data below |

This matches DOJ's own API page banner: more endpoints are promised after the eFile migration finishes. **Do not depend on the broken JSON endpoints.**

Rate limit: **5 requests / 10 seconds**, rolling window, reproduced live via an actual `429`.

## Real primary source: 4 daily bulk files

`https://efile.fara.gov/bulk/zip/{name}.csv.zip`, ISO-8859-1 encoded, `Last-Modified` = day-of, ZIP contains exactly one CSV member. Downloaded and inspected directly on 2026-08-21:

| File | True CSV data rows | Exact header |
|---|---|---|
| `FARA_All_Registrants.csv.zip` | 7,076 | `Registration Number, Registration Date, Termination Date, Name, Business Name, Address 1, Address 2, City, State, Zip` |
| `FARA_All_RegistrantDocs.csv.zip` | 153,603 | `Date Stamped, Registrant Name, Registration Number, Document Type, Short Form Name, Foreign Principal Name, Foreign Principal Country, URL` |
| `FARA_All_ShortForms.csv.zip` | 44,606 | `Short Form Termination Date, Short Form Date, Short Form Last Name, Short Form First Name, Registration Number, Registration Date, Registrant Name, Address 1, Address 2, City, State, Zip` |
| `FARA_All_ForeignPrincipals.csv.zip` | 17,739 | `Foreign Principal Termination Date, Foreign Principal, Foreign Principal Registration Date, Country/Location Represented, Registration Number, Registrant Date, Registrant Name, Address 1, Address 2, City, State, Zip` |

Registrants (7,076) = Active (536) + Terminated (6,540) JSON totals exactly — internally consistent.

**Important correction, confirmed by building the real downloader (build step 2):** counting rows with `wc -l` overstates every one of these files, because a real minority of rows carry an embedded newline inside a quoted field (e.g. a `Name` value literally containing `"Sonoran Policy Group, LLC D/B/A Stryk Global Diplomacy\n\n"`). Confirmed by parsing with Python's `csv` module: 1 such row in `Registrants` (naive line count read 7,077, not 7,076), 106 in `RegistrantDocs` (naive: 153,709), 12 in `ShortForms` (naive: 44,618), 40 in `ForeignPrincipals` (naive: 17,779). **Never count or split these files by newline — always parse with a real CSV reader.** The ingest/normalize code already does this correctly (`csv.reader`/`csv.DictReader`); this note exists only because the initial recon pass in this document used `wc -l` and reported the inflated figures before the downloader caught the discrepancy.

## Document Type vocabulary (confirmed complete, closed set)

The API's 10 uppercase codes (from `DocumentTypes/html`) map 1:1 onto the bulk CSV's 10 human labels — confirmed by cross-referencing both lists directly, no unmapped values either direction:

| API code | CSV label | Count in bulk (all-time) |
|---|---|---|
| `SHORT-FORM` | Short-Form | 43,350 |
| `SUPPLEMENTAL_STATEMENT` | Supplemental Statement | 41,330 |
| `INFORMATIONAL_MATERIALS` | Informational Materials | 21,181 |
| `EXHIBIT_AB` | Exhibit AB | 16,758 |
| `AMENDMENT` | Amendment | 15,666 |
| `DISSEMINATION_REPORT` | Dissemination Report | 9,022 |
| `REGISTRATION_STATEMENT` | Registration Statement | 3,832 |
| `EXHIBIT_C` | Exhibit C | 2,343 |
| `EXHIBIT_D` | Exhibit D | 113 |
| `CONFLICT_PROVISION` | Conflict Provision | 8 |

This vocabulary is small, stable, and fully confirmed closed — `reconcile.py`'s fail-loud pre-flight check is appropriate and safe here.

## Country/location field — NOT a coded dimension (correction vs. initial assumption)

The bulk CSVs' `Country/Location Represented` (ForeignPrincipals) and `Foreign Principal Country` (RegistrantDocs) fields are **plain free text**, not FARA's internal country-code scheme (that scheme only appears to back the broken JSON `Countries` endpoint and its search-filter UI — it is never present in the data we actually ingest). Cross-referencing both files found **282 distinct values**, including:

- Real historical-name variants that coexist rather than being normalized: `GREAT BRITAIN` (548 occurrences) alongside `UNITED KINGDOM` (72); `USSR` (302) alongside `RUSSIA` (248); `KOREA, SOUTH` / `KOREA, NORTH`.
- At least one dummy/test entry: `UNITED KINGDOM OF CORALLAND` (1 occurrence — not a real country).
- **9 outright column-shift data-quality artifacts**: 8 values that are dates (`01/10/1947`, `04/20/1993`, `08/03/2021`, `08/22/2022`, `08/26/2022`, `09/03/1957`, `09/28/2022`, `10/12/2022`) and 1 that's a bare number (`7383`) — evidence of a misaligned column somewhere in DOJ's own export for a handful of historical rows.

**Design consequence:** treat this as free text, always. Store the raw string verbatim on every row (no FK, no fail-loud reconciliation — a closed-vocabulary assumption would be actively wrong here, given the confirmed garbage values). `seed_data/countries.csv` (273 rows, the 282 observed values minus the 9 anomalies above) seeds a `countries` reference table for `/api/countries` and UI filter dropdowns only; the loader auto-registers any newly observed value it hasn't seen before rather than rejecting it.

## Zip field — confirmed inconsistent, refined

Live-checked the full `Registrants/json/Active` response (536 rows) directly:

- 464 rows: `Zip` is a bare JSON number (e.g. `35243`)
- 46 rows: `Zip` is a JSON string (e.g. `"07103"`, leading zero preserved)
- **26 rows: the `Zip` key is missing from the row entirely** — not null, absent.

Normalize to text unconditionally; use `.get('Zip')` (never direct indexing) when parsing this JSON. The bulk CSVs don't have this problem since CSV cells are always plain text.

## Date field — one confirmed malformed value

Parsed `Date Stamped` across all 153,603 well-formed rows in `FARA_All_RegistrantDocs.csv`: **1 row** has a corrupted year (`11/16/0200` instead of presumably `11/16/2001`, judging by the adjacent malformed URL segment `2001116` instead of an 8-digit `YYYYMMDD`). Rate is negligible (1 in 153,603) but real — date parsing must log-and-flag on failure, never raise and abort the whole load.

## PDF availability — confirmed rate and pattern

`URL` in `FARA_All_RegistrantDocs.csv` is either a real `https://...` link or the literal sentinel string **`Available-FARA-Public-Office`** — confirmed exactly one sentinel value, no other placeholder variants. **27,814 of 153,603 rows (18.1%)** carry this sentinel, i.e. the document exists only in DOJ's physical office, not online. Distribution by decade of `Date Stamped` (rows with the sentinel):

| Decade | Office-only rows |
|---|---|
| 1940s | 197 |
| 1950s | 540 |
| 1960s | 1,267 |
| 1970s | 2,580 |
| 1980s | 7,350 |
| 1990s | 9,658 |
| 2000s | 6,222 |

This gap extends well into the 2000s — materially later than a "pre-2008" assumption would suggest. Compute `pdf_available` directly from whether `URL` starts with `http` (not solely from a fetch attempt's HTTP status) — this is a known, quantified structural gap in FARA's own archive, not an ingest failure, and should never be retried or treated as an error.

## PDF hosting is stable and unauthenticated

Every real `http`-prefixed URL sampled (oldest tested: `55-Exhibit-AB-19420701-CXMAYE01.pdf`, dated 1942-07-01) returned `200` on direct unauthenticated `curl`. Filename sequence suffixes are **not always plain integers** — older documents use alphanumeric codes (e.g. `CXMAYE01`, `DPYW5E93`), so `sequence_in_filename` should be stored as text, not an integer.

## Registrants file — one confirmed duplicate registration number

Loading the real `2026-08-21` `FARA_All_Registrants.csv` (build step 5) surfaced a real
data-quality bug: **Registration Number 5769** (`O'Malley, Sheila`) appears on **two rows**
in the same snapshot, identical except for `Termination Date` (`08/01/2008` vs.
`09/19/2006`, the latter matching the row's own `Registration Date` — likely a data-entry
error upstream). Rate: 1 duplicate in 7,076 rows. Without deduplication, a loader that
processes rows in file order would alternate between the two rows' values on every re-run
instead of ever settling — confirmed by reproducing exactly this flip-flop before fixing it.
`load_registrants` now deduplicates by Registration Number before loading, keeping the last
occurrence in the file (consistent with the last-write-wins convention used throughout), and
reports the collapse count. Re-running the real file three times in a row now settles to
`unchanged` immediately, proven live.

## PDF sizes — a real outlier risk, confirmed live

Downloading real recent filings (build step 7) turned up a genuine capacity-planning
finding: most filing PDFs are a few hundred KB to ~10 MB, but **some `Informational
Materials` filings are enormous multimedia dissemination copies** — one observed at
**2.3 GB**, several others at 100–220 MB, against typical filings well under 10 MB. Of 134
documents filed in a 14-day window, 5 exceeded 50 MB. Without a guard, 249 downloaded
documents (mostly from a 14-day window plus a small active-registrants backfill sample)
totalled **3.6 GB** — almost entirely driven by a handful of outliers, not the median
document. The downloader now streams responses and skips (not downloads) anything over
`--max-bytes` (default 50 MB, checked via `Content-Length` where present and enforced
during the read regardless, since headers can be absent or wrong), recording `too_large`
as a distinct terminal status — the same size 250-document batch dropped to ~500 MB with
the guard active. This is a real, load-bearing finding for both local disk usage and the
eventual object-storage cost/deployment sizing (`docs/schema.md`/deployment planning), not
a hypothetical edge case.

## Backfill ordering — a real pacing characteristic, confirmed live

`--mode backfill`'s active-registrants-first, most-recent-first ordering means a modest
batch size can be entirely consumed by *recent* filings from active registrants before
ever reaching genuinely historical documents — confirmed live: a 250-document backfill
batch (after the 134 already fetched by `new` mode) still only reached documents filed in
August 2026, none older. This is expected, not a bug: active registrants alone generate
enough current filing volume to fill a small batch many times over. Reaching the ~154K-row
historical archive requires either a much larger `--batch-size` or repeated invocations
over time — consistent with the plan's "run at whatever pace you choose" design for this
manual, unscheduled path.

## Confidence summary

Everything above is **confirmed live** via direct curl/download/parse against `efile.fara.gov` on 2026-08-21, including full-corpus counts (not samples) for the Zip-type breakdown, date-malformation rate, PDF-availability rate, and country-value anomalies. See `docs/extraction.md` for PDF-content-layer findings (metadata cover pages, OCR eras, form structure).
