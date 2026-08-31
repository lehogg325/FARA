from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime, timedelta

import httpx

from fara_ingest.archive import RawArchive, sha256_bytes
from fara_ingest.manifest import Manifest
from fara_ingest.rate_limit import TokenBucket
from fara_ingest.sources.fara.constants import ENCODING, JURISDICTION

USER_AGENT = "fara-ingest/0.1 (https://github.com/lehogg325/FARA)"

# Politeness pacing for the static docs host — it isn't officially rate-limited
# (docs/api-notes.md, unlike the 5-req/10s JSON API), but hammering it isn't
# reasonable either.
DOCS_HOST_MAX_TOKENS = 10
DOCS_HOST_REFILL_SECONDS = 1.0

DEFAULT_NEW_WINDOW_DAYS = 14
DEFAULT_BATCH_SIZE = 200


@dataclass
class Candidate:
    url: str
    registration_number: int
    document_type: str
    date_stamped_raw: str


@dataclass
class DownloadSummary:
    candidates: int
    verified: int
    unavailable: int
    too_large: int
    failed: int
    skipped_already_terminal: int


def _read_zip_csv_rows(raw_zip: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        csv_bytes = zf.read(zf.namelist()[0])
    return list(csv.DictReader(io.StringIO(csv_bytes.decode(ENCODING))))


def _active_registration_numbers(registrants_rows: list[dict[str, str]]) -> set[int]:
    result = set()
    for row in registrants_rows:
        if not row.get("Termination Date", "").strip():
            try:
                result.add(int(row["Registration Number"].strip()))
            except (KeyError, ValueError):
                continue
    return result


def select_candidates(
    registrant_docs_rows: list[dict[str, str]],
    *,
    mode: str,
    active_registration_numbers: set[int] | None = None,
    window_days: int = DEFAULT_NEW_WINDOW_DAYS,
    today: date_ | None = None,
    backfill_from_date: date_ | None = None,
) -> list[Candidate]:
    """`new` mode: only documents actually filed within the last `window_days`
    (by Date Stamped) — NOT "rows not yet downloaded," which on a first-ever
    run would be the entire ~150K-row historical backlog. `backfill` mode:
    every real-URL row (optionally bounded below by `backfill_from_date`, for
    a scoped sweep like "2025 onward, nothing older"), active registrants'
    documents first (most recent date stamped first within each group), for
    the manual, unscheduled sweep.
    """
    today = today or date_.today()
    cutoff = today - timedelta(days=window_days)

    real_url_rows = [r for r in registrant_docs_rows if r.get("URL", "").strip().startswith("http")]

    if mode == "new":
        selected = []
        for row in real_url_rows:
            try:
                stamped = datetime.strptime(row["Date Stamped"].strip(), "%m/%d/%Y").date()
            except ValueError:
                continue  # confirmed live: 1 malformed date exists (docs/api-notes.md) — excluded, not crashed on
            if stamped >= cutoff:
                selected.append(row)
    elif mode == "backfill":
        active = active_registration_numbers or set()

        def row_date(row: dict[str, str]) -> date_:
            try:
                return datetime.strptime(row["Date Stamped"].strip(), "%m/%d/%Y").date()
            except ValueError:
                return date_.min

        backfill_rows = real_url_rows
        if backfill_from_date is not None:
            backfill_rows = [r for r in backfill_rows if row_date(r) >= backfill_from_date]

        def sort_key(row: dict[str, str]) -> tuple:
            try:
                regnum = int(row["Registration Number"].strip())
            except ValueError:
                regnum = -1
            # Active registrants first (False < True); within each group, most
            # recently filed first — Date Stamped is MM/DD/YYYY so a plain
            # descending string sort isn't chronological, hence the parse.
            return (regnum not in active, -row_date(row).toordinal())

        selected = sorted(backfill_rows, key=sort_key)
    else:
        raise ValueError(f"unknown mode {mode!r}, expected 'new' or 'backfill'")

    result = []
    for row in selected:
        try:
            regnum = int(row["Registration Number"].strip())
        except (KeyError, ValueError):
            continue  # confirmed 0 of these in RegistrantDocs today, but never crash on a future anomaly
        result.append(
            Candidate(
                url=row["URL"].strip(),
                registration_number=regnum,
                document_type=row.get("Document Type", "").strip(),
                date_stamped_raw=row.get("Date Stamped", "").strip(),
            )
        )
    return result


def _archive_key_for_pdf(registration_number: int, url: str) -> str:
    filename = url.rsplit("/", 1)[-1]
    return f"fara/docs/{registration_number}/{filename}"


# Confirmed live: some 'Informational Materials' filings are enormous
# multimedia dissemination copies — one observed at 2.3 GB, several at
# 100-220 MB, against a typical filing PDF of well under 10 MB
# (docs/api-notes.md). A weekly job's runtime and storage need to stay
# predictable, so anything over this is skipped, not downloaded.
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def download_one(
    candidate: Candidate,
    *,
    archive: RawArchive,
    manifest: Manifest,
    client: httpx.Client,
    bucket: TokenBucket,
    force: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """Returns the terminal status: 'verified', 'unavailable', 'too_large',
    'failed', or 'skipped' (already terminal, force not set)."""
    existing = manifest.get_pdf_status(candidate.url)
    if existing in ("verified", "unavailable", "too_large") and not force:
        return "skipped"

    manifest.start_pdf(
        candidate.url,
        registration_number=candidate.registration_number,
        document_type=candidate.document_type,
        date_stamped=candidate.date_stamped_raw,
    )

    bucket.acquire()
    try:
        with client.stream("GET", candidate.url) as response:
            if response.status_code == 404:
                # Confirmed live: some listed URLs 404 despite being in the
                # CSV — a known structural gap, terminal, never retried
                # (docs/api-notes.md).
                manifest.mark_pdf_unavailable(candidate.url, http_status=404)
                return "unavailable"

            if response.status_code != 200:
                manifest.mark_pdf_failed(
                    candidate.url, error_message=f"HTTP {response.status_code}", http_status=response.status_code
                )
                return "failed"

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                manifest.mark_pdf_too_large(candidate.url, byte_size=int(content_length))
                return "too_large"

            chunks = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    # Content-Length was absent, wrong, or lied about — this is
                    # the actual safety net, not just the header fast path.
                    manifest.mark_pdf_too_large(candidate.url, byte_size=total)
                    return "too_large"
                chunks.append(chunk)
            raw = b"".join(chunks)
    except httpx.HTTPError as e:
        manifest.mark_pdf_failed(candidate.url, error_message=str(e))
        return "failed"

    key = _archive_key_for_pdf(candidate.registration_number, candidate.url)
    archive.write_atomic(key, raw)
    manifest.mark_pdf_verified(
        candidate.url, archive_key=key, sha256=sha256_bytes(raw), byte_size=len(raw), http_status=200
    )
    return "verified"


def run_docs_download(
    *,
    archive: RawArchive,
    manifest: Manifest,
    registrant_docs_zip: bytes,
    registrants_zip: bytes | None = None,
    mode: str = "new",
    window_days: int = DEFAULT_NEW_WINDOW_DAYS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backfill_from_date: date_ | None = None,
    client: httpx.Client | None = None,
) -> DownloadSummary:
    registrant_docs_rows = _read_zip_csv_rows(registrant_docs_zip)
    active_regnums = None
    if mode == "backfill":
        if registrants_zip is None:
            raise ValueError("backfill mode requires registrants_zip for active-first ordering")
        active_regnums = _active_registration_numbers(_read_zip_csv_rows(registrants_zip))

    candidates = select_candidates(
        registrant_docs_rows,
        mode=mode,
        active_registration_numbers=active_regnums,
        window_days=window_days,
        backfill_from_date=backfill_from_date,
    )
    candidates = candidates[:batch_size]

    owns_client = client is None
    http_client = client or httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    bucket = TokenBucket(max_tokens=DOCS_HOST_MAX_TOKENS, refill_seconds=DOCS_HOST_REFILL_SECONDS)

    verified = unavailable = too_large = failed = skipped = 0
    try:
        for candidate in candidates:
            status = download_one(
                candidate, archive=archive, manifest=manifest, client=http_client, bucket=bucket,
                force=force, max_bytes=max_bytes,
            )
            if status == "verified":
                verified += 1
            elif status == "unavailable":
                unavailable += 1
            elif status == "too_large":
                too_large += 1
            elif status == "failed":
                failed += 1
            else:
                skipped += 1
    finally:
        if owns_client:
            http_client.close()

    return DownloadSummary(
        candidates=len(candidates),
        verified=verified,
        unavailable=unavailable,
        too_large=too_large,
        failed=failed,
        skipped_already_terminal=skipped,
    )
