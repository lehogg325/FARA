from __future__ import annotations

import sys
from datetime import date as date_

import click

from fara_ingest.archive_factory import get_archive
from fara_ingest.config import Config
from fara_ingest.manifest import Manifest
from fara_ingest.sources.fara.bulk import BulkDownloadError, archive_key, download_bulk_dataset
from fara_ingest.sources.fara.client import RateLimitedClient
from fara_ingest.sources.fara.constants import DATASETS, JURISDICTION
from fara_ingest.sources.fara.docs import DEFAULT_BATCH_SIZE, DEFAULT_MAX_BYTES, DEFAULT_NEW_WINDOW_DAYS, run_docs_download
from fara_ingest.sources.fara.poll import poll_registrants
from fara_ingest.sources.fara.verify import VerificationFailed, verify_registrant_counts


@click.group()
def main() -> None:
    """FARA ingest CLI."""


@main.command()
@click.option(
    "--dataset",
    "datasets",
    multiple=True,
    type=click.Choice(sorted(DATASETS)),
    help="Dataset to download. Repeatable. Defaults to all datasets.",
)
@click.option("--force", is_flag=True, help="Re-download even if today's snapshot is already verified.")
def bulk(datasets: tuple[str, ...], force: bool) -> None:
    """Download and archive the FARA bulk CSV files."""
    cfg = Config.from_env()
    archive = get_archive(cfg)
    manifest = Manifest(cfg.manifest_path)

    targets = list(datasets) if datasets else sorted(DATASETS)
    exit_code = 0
    for dataset in targets:
        try:
            result = download_bulk_dataset(dataset, archive=archive, manifest=manifest, force=force)
        except BulkDownloadError as e:
            click.echo(f"FAILED           {dataset}: {e}", err=True)
            exit_code = 1
            continue
        click.echo(f"{result.status.upper():<16} {dataset:<20} rows={result.row_count} key={result.archive_key}")
    sys.exit(exit_code)


@main.command()
@click.option("--mode", type=click.Choice(["new", "backfill"]), default="new", show_default=True)
@click.option("--window-days", default=DEFAULT_NEW_WINDOW_DAYS, show_default=True, help="'new' mode: how far back by Date Stamped.")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, show_default=True)
@click.option("--max-bytes", default=DEFAULT_MAX_BYTES, show_default=True, help="Skip (not download) any file larger than this.")
@click.option("--from-date", default=None, help="'backfill' mode: only documents filed on/after this date (YYYY-MM-DD).")
@click.option("--force", is_flag=True, help="Re-attempt URLs already verified/unavailable/too_large.")
def docs(mode: str, window_days: int, batch_size: int, max_bytes: int, from_date: str | None, force: bool) -> None:
    """Download filing PDFs. Default 'new' mode only fetches documents filed
    within --window-days — never the historical backlog. 'backfill' mode
    sweeps everything, active registrants first, and is never invoked by the
    scheduled workflow (see docs/api-notes.md)."""
    cfg = Config.from_env()
    archive = get_archive(cfg)
    manifest = Manifest(cfg.manifest_path)

    docs_snapshot = manifest.get_latest_verified_snapshot(JURISDICTION, "registrant_docs")
    if docs_snapshot is None:
        click.echo("no verified registrant_docs bulk archive found — run `fara-ingest bulk` first", err=True)
        raise SystemExit(1)
    registrant_docs_zip = archive.read_bytes(archive_key("registrant_docs", docs_snapshot))

    registrants_zip = None
    if mode == "backfill":
        reg_snapshot = manifest.get_latest_verified_snapshot(JURISDICTION, "registrants")
        if reg_snapshot is None:
            click.echo("no verified registrants bulk archive found — run `fara-ingest bulk` first", err=True)
            raise SystemExit(1)
        registrants_zip = archive.read_bytes(archive_key("registrants", reg_snapshot))

    summary = run_docs_download(
        archive=archive,
        manifest=manifest,
        registrant_docs_zip=registrant_docs_zip,
        registrants_zip=registrants_zip,
        mode=mode,
        window_days=window_days,
        batch_size=batch_size,
        max_bytes=max_bytes,
        backfill_from_date=date_.fromisoformat(from_date) if from_date else None,
        force=force,
    )
    click.echo(
        f"candidates={summary.candidates} verified={summary.verified} unavailable={summary.unavailable} "
        f"too_large={summary.too_large} failed={summary.failed} skipped={summary.skipped_already_terminal}"
    )


@main.command()
def poll() -> None:
    """Poll the two working JSON endpoints. Diagnostic only — archives raw
    responses verbatim but never loads them into Postgres."""
    cfg = Config.from_env()
    archive = get_archive(cfg)
    client = RateLimitedClient()
    try:
        result = poll_registrants(archive=archive, client=client)
    finally:
        client.close()
    click.echo(f"active={result.active_count} terminated={result.terminated_count}")


@main.command()
@click.option("--snapshot-date", default=None, help="Defaults to today (UTC).")
@click.option("--tolerance", default=2, show_default=True, help="Max allowed bulk-vs-poll count difference.")
def verify(snapshot_date: str | None, tolerance: int) -> None:
    """Cross-check the day's bulk registrant count against a live JSON poll."""
    cfg = Config.from_env()
    archive = get_archive(cfg)
    manifest = Manifest(cfg.manifest_path)
    snapshot_date = snapshot_date or date_.today().isoformat()

    client = RateLimitedClient()
    try:
        poll_result = poll_registrants(archive=archive, client=client)
    finally:
        client.close()

    try:
        result = verify_registrant_counts(manifest, snapshot_date, poll_result, tolerance=tolerance)
    except VerificationFailed as e:
        click.echo(f"VERIFY FAILED: {e}", err=True)
        sys.exit(1)

    click.echo(
        f"VERIFY OK  bulk_registrants={result.bulk_registrant_count} "
        f"poll_active={result.poll_active_count} poll_terminated={result.poll_terminated_count} "
        f"poll_total={result.poll_total} diff={result.difference} (tolerance={result.tolerance})"
    )


if __name__ == "__main__":
    main()
