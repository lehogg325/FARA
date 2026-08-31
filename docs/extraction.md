# Document-mining reconnaissance findings

Sampled real PDFs across eras (1942 → 2026, ~20 documents, all document types with real URLs) via direct download and `pdfplumber` text extraction on 2026-08-21. This grounds the `pipeline/extract` design — the metadata-cover-page pattern below in particular changes the extraction approach materially from a naive "old = scan, new = native text" assumption.

## Three distinct eras, not two

**Era 1 — pre-~2011: synthetic metadata cover page + genuinely scanned body.**

Every pre-2011 document sampled (7 of 7, spanning the 1940s–2010) has this exact structure:

- **Page 1** is a DOJ-system-generated (not part of the original filing) cover page, always starting `Document Metadata\n` followed by exactly 18 `KEY=VALUE` lines in a fixed order, then a boilerplate ADA-accessibility notice. Confirmed identical field set across every sample:
  ```
  REGISTRATION NUMBER, REGISTRANT NAME, ALIAS, SUPPLEMENTAL END DATE, DOING BUSINESS AS,
  DOCUMENT TYPE, SHORT FORM NAME, SHORT FORM REGISTRATION DATE, SHORT FORM STATUS,
  SHORT FORM TERMINATION DATE, FOREIGN PRINCIPAL NAME, FOREIGN PRINCIPAL COUNTRY,
  FP STATUS, FP REGISTRATION DATE, FP TERMINATION DATE, REGISTRANT STATUS,
  REGISTRATION DATE, REGISTRANT TERMINATION DATE, DATE STAMPED
  ```
  This is 100%-reliable, free structured data — trivial `KEY=VALUE` line parsing, no OCR or LLM needed. It also exposes fields the bulk CSVs don't carry directly (e.g. `FP STATUS`, `REGISTRANT STATUS` as explicit values rather than derived from a termination-date null-check) — a genuine bonus source.
- **Pages 2+** are pure scanned images: confirmed `0` extractable characters via native text extraction, `images=1` per page, on every sample checked (e.g. a 32-page 1985 Supplemental Statement has 0 native chars on pages 2–32). **These need OCR** to recover any content.

**Era 2 — ~2011: transitional, no cover page, embedded but garbled text.** One 2011 sample (`5938-Supplemental-Statement-20111231-6.pdf`) has no metadata cover page but its "native" extracted text is visibly corrupted (`*__I>_rf_i«^^` for what should be a form header) — DOJ appears to have started embedding an OCR'd text layer directly into the PDF around this point, at low quality. Native extraction will return *something* here, but it can be garbage — quality detection must not treat "text present" as "text trustworthy."

**Era 3 — ~2012 onward: born-digital, clean native text.** Confirmed clean, fully structured, readable text from 2012 forward (and current 2026 filings) — e.g. `Received by NSD/FARA Registration Unit 12/31/2012 8:24:34 PM ... U.S. Department of Justice Supplemental Statement`. This is the easy case: native extraction alone via `pdfplumber` is complete and reliable.

**Design consequence for `fara-extract text`:** don't branch purely on document date. Per page: (1) check for the `Document Metadata\n` + `REGISTRATION NUMBER=` signature on page 1 — if present, parse it directly as structured fields (route to a dedicated `metadata_cover` rule extractor, `extractor_version='metadata-cover-v1'`) and exclude that page from body text; (2) for every remaining page, attempt native extraction, and only fall back to OCR (`pdf2image` + `pytesseract`) when native char count is near-zero; (3) always run a garbled-text heuristic (e.g. ratio of dictionary-recognizable word tokens, or proportion of non-alphanumeric runs) on whatever text results, native or OCR, and set `quality_flag='low_confidence'` when it fires — Era 2's embedded-but-garbled text will only be caught this way, not by the native/OCR branch alone. `document_text.extraction_method` becomes `'native'`, `'ocr'`, or `'mixed'` (native cover + OCR/native-garbled body).

## Modern form structure (confirmed real section headers, for the rule-based extractor)

Sampled a complete document set from one real, recent registrant (Mercury Public Affairs, reg 6170) — Registration Statement (2013), Amendment, Exhibit AB, Short Form, Supplemental Statement (all 2026) — all born-digital, all cleanly extracted:

- Registration Statement: `OMB NO. 1124-0001` / `Registration Statement` / section `I-REGISTRANT` / `1. Name of Registrant` — numbered-item structure confirmed present and extractable.
- Supplemental Statement: `OMB No. 1124-0002` / `For 6 Month Period Ending {date}` / `I- REGISTRANT` — same numbered-item pattern, period-scoped.
- Exhibit AB: `OMB No. 1124-0006` / `Exhibit A to Registration Statement`.
- Short Form: `OMB No. 1124-0005` / `Short Form Registration Statement`.
- Amendment: references `Amendment to Registration Statement`.

Each form type carries a distinct, stable OMB control number — a reliable signal (in addition to the CSV's own `Document Type`) for which rule-extractor schema to apply. **Known text-layer quirk:** even clean born-digital PDFs have PDF-internal kerning artifacts, e.g. `"U.S. Department ofJ ustice"` (missing space, split word) appearing verbatim in extracted text across multiple samples — the rule-based extractor must match section headers with whitespace-tolerant patterns, not exact substrings.

The exact item-by-item field layout within `I-REGISTRANT`, `II-FOREIGN PRINCIPAL`, etc. sections (compensation line items, activity-description items, political-contribution items) needs to be mapped from a full read of one real Registration Statement and one real Supplemental Statement — do this as the first task of build step 9 (rule-based field extraction), using the already-downloaded `6170-Registration-Statement-20130514-1.pdf` and `6170-Supplemental-Statement-20260722-28.pdf` as the reference documents, since both are confirmed clean and complete.

## Live proof, build step 8: 239 real documents, 0 crashes

Running `fara-extract text` against 239 real downloaded PDFs (recent filings, all
born-digital era) produced `native/ok` (219), `mixed/ok` (11), `native/low_confidence` (9),
zero failures. Hand-verified three real cases:

- **`native/ok`**: extracted text matched the source PDF byte-for-byte (reg 7435,
  Supplemental Statement).
- **`mixed/ok`**: a real Amendment where page 1 is born-digital (3,944 native chars) and
  pages 2-3 are scanned/image-only (0 native chars each) — OCR correctly recovered a
  signature-page's printed text ("8/12/2026 Misti Borchers"), with only the actual
  handwritten signature itself garbling, exactly as expected.
- **`native/low_confidence`**: a genuinely important, unanticipated finding — a real
  Informational Materials filing (reg 5860) is a **bilingual French/Arabic press
  communiqué** from an armed political group. Native extraction handles the French text
  cleanly but the Arabic script garbles into meaningless Latin-character noise. The
  `is_garbled` heuristic (calibrated only against the Era-2 English-OCR-noise sample)
  correctly flagged this too — a different failure mode (multi-script extraction, not
  DOJ-embedded-OCR quality) it was never tuned against. This generalization is a good
  sign, but also a concrete reminder that **non-Latin-script documents are a real,
  recurring category** in FARA's Informational Materials (given the range of foreign
  principal countries), not a one-off — future extraction stages (rules/LLM) should
  expect and handle low-confidence, script-mixed text rather than assume clean English.

## Build step 9: rule-based field extraction — real findings

Mapped the actual numbered-item form layout from real fixture PDFs rather than assuming
it (`era3-registration-statement.pdf`, `era3-supplemental-statement.pdf`,
`era3-short-form.pdf`, `era3-exhibit-ab.pdf`). Two findings materially shaped the design:

**Checkbox glyphs are not reliably parseable.** Yes/No checkboxes render as garbled
single characters whose meaning isn't stable — e.g. `Yes • No M`, `Yes D No H`, `Yes S No
D` all appear in the same document, and the same conceptual "checked" state maps to
different extracted characters in different fields (confirmed by cross-referencing against
attachments we know are populated). **Decision: never attempt to parse checkbox state.**
Instead, presence of real data (contribution rows, narrative text) is used as the signal —
if a table has rows, something was disclosed; if not, no claim is made either way.

**Political contributions are the flagship target — confirmed real and valuable across all
three filer-side document types.** Registration Statement (Item 10(c)), Supplemental
Statement (Item 15(c)), and Short-Form (Item 15) all disclose money-to-political-campaigns
data in a table, with a shared statutory question phrase ("primary election, convention, or
caucus") but different column layouts and item numbers. This is genuinely new information —
none of it exists anywhere in the bulk CSVs. Real hand-verified example: Mercury Public
Affairs short-form filer Bryan Lanza's `$3,000.00` contribution to "Emmer for Congress" on
`06/09/2026` matched exactly, byte-for-byte against the source PDF, description text and
all (down to a wrapped-line artifact reproducing in both).

**A real false-positive bug, caught by testing against the full dev database, not just
fixtures.** The table-header row itself is unreliable as an anchor — a real appendix table
had "Political" and "Organization/Candidate" split by column-wrap with other text inserted
between them. Anchoring on the stable statutory question phrase instead fixed that, but
introduced a new bug: a short or empty contributions section let the fixed extraction
window run past its own table boundary into the next section (`V - INFORMATIONAL
MATERIALS`) and misread that section's budget-dollar-figures as political contributions —
one document showed a "$12,587,064.00 contribution" that was actually an informational-
materials budget line. Fixed by stopping the window at the next section heading. This was
invisible in fixture-only testing (all fixtures happened to have either substantial
contribution data or none at all with a boundary already nearby) and only surfaced when
run against the full ~93-document real candidate set — a concrete argument for testing
extraction logic against volume, not just the curated fixture set.

## Confidence summary

The three-era structure, the metadata-cover-page format (exact 18 keys, confirmed identical across 7 independent samples spanning 1942–2010), the Era-2 garbling, and the OMB-number-per-form-type mapping are all **confirmed live** from real downloaded PDFs, not inferred. The precise sub-item layout inside each form's numbered sections is **not yet mapped** — that's explicit build-step-9 work, not assumed here.
