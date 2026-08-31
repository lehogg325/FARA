from __future__ import annotations

import anthropic
import click
from fara_ingest.archive_factory import get_archive
from fara_ingest.config import Config as IngestConfig
from fara_ingest.manifest import Manifest as IngestManifest

from fara_extract.db import get_connection
from fara_extract.fields_llm import DEFAULT_MODEL
from fara_extract.run_contacts_stage import run_contacts_stage
from fara_extract.run_fields_llm_stage import run_fields_llm_stage
from fara_extract.run_fields_rules_stage import run_fields_rules_stage
from fara_extract.run_text_stage import run_text_stage
from fara_extract.run_topics_stage import run_topics_stage

_FROM_DATE_HELP = "'backfill' mode: only documents filed on/after this date (YYYY-MM-DD)."


@click.group()
def main() -> None:
    """FARA document-mining CLI."""


@main.command(name="text")
@click.option("--mode", type=click.Choice(["new", "backfill"]), default="new", show_default=True)
@click.option("--batch-size", default=200, show_default=True)
@click.option("--from-date", default="1900-01-01", show_default=True, help=_FROM_DATE_HELP)
def text_cmd(mode: str, batch_size: int, from_date: str) -> None:
    """Extract text (native or OCR) from downloaded PDFs into document_text."""
    ingest_cfg = IngestConfig.from_env()
    archive = get_archive(ingest_cfg)
    ingest_manifest = IngestManifest(ingest_cfg.manifest_path)
    conn = get_connection()
    try:
        summary = run_text_stage(
            conn=conn, ingest_archive=archive, ingest_manifest=ingest_manifest,
            mode=mode, batch_size=batch_size, from_date=from_date,
        )
    finally:
        conn.close()
    click.echo(
        f"candidates={summary.candidates} extracted={summary.extracted} "
        f"no_pdf_available={summary.no_pdf_available} failed={summary.failed}"
    )


@main.command(name="fields-rules")
@click.option("--mode", type=click.Choice(["new", "backfill"]), default="new", show_default=True)
@click.option("--batch-size", default=200, show_default=True)
@click.option("--from-date", default="1900-01-01", show_default=True, help=_FROM_DATE_HELP)
def fields_rules_cmd(mode: str, batch_size: int, from_date: str) -> None:
    """Rule-based structured field extraction (political contributions,
    agreement dates) from already-extracted document text."""
    conn = get_connection()
    try:
        summary = run_fields_rules_stage(conn=conn, mode=mode, batch_size=batch_size, from_date=from_date)
    finally:
        conn.close()
    click.echo(
        f"candidates={summary.candidates} processed={summary.processed} "
        f"fields_written={summary.fields_written} failed={summary.failed}"
    )


@main.command(name="fields-llm")
@click.option("--mode", type=click.Choice(["new", "backfill"]), default="new", show_default=True)
@click.option("--batch-size", default=50, show_default=True)
@click.option("--model", default=DEFAULT_MODEL, show_default=True)
@click.option("--from-date", default="1900-01-01", show_default=True, help=_FROM_DATE_HELP)
def fields_llm_cmd(mode: str, batch_size: int, model: str, from_date: str) -> None:
    """LLM-assisted narrative field extraction (Exhibit AB nature-of-activities,
    political-activity description, compensation terms)."""
    conn = get_connection()
    llm_client = anthropic.Anthropic()
    try:
        summary = run_fields_llm_stage(
            conn=conn, llm_client=llm_client, mode=mode, batch_size=batch_size, model=model, from_date=from_date
        )
    except anthropic.AuthenticationError as e:
        click.echo(f"Anthropic API authentication failed: {e}", err=True)
        raise SystemExit(1) from e
    finally:
        conn.close()
    click.echo(
        f"candidates={summary.candidates} processed={summary.processed} "
        f"fields_written={summary.fields_written} failed={summary.failed}"
    )


@main.command(name="contacts")
@click.option("--mode", type=click.Choice(["new", "backfill"]), default="new", show_default=True)
@click.option("--batch-size", default=200, show_default=True)
@click.option("--model", default=DEFAULT_MODEL, show_default=True)
@click.option("--from-date", default="1900-01-01", show_default=True, help=_FROM_DATE_HELP)
def contacts_cmd(mode: str, batch_size: int, model: str, from_date: str) -> None:
    """Reportable-contact extraction (Item 11 Date/Contact Method/Purpose table)
    — rule-based pre-filter for populated tables, LLM structuring of the rest."""
    conn = get_connection()
    llm_client = anthropic.Anthropic()
    try:
        summary = run_contacts_stage(
            conn=conn, llm_client=llm_client, mode=mode, batch_size=batch_size, model=model, from_date=from_date
        )
    except anthropic.AuthenticationError as e:
        click.echo(f"Anthropic API authentication failed: {e}", err=True)
        raise SystemExit(1) from e
    finally:
        conn.close()
    click.echo(
        f"candidates={summary.candidates} processed={summary.processed} "
        f"windows_found={summary.windows_found} contacts_written={summary.contacts_written} failed={summary.failed}"
    )


@main.command(name="topics")
@click.option("--mode", type=click.Choice(["new", "backfill"]), default="new", show_default=True)
@click.option("--batch-size", default=200, show_default=True)
@click.option("--model", default=DEFAULT_MODEL, show_default=True)
@click.option("--from-date", default="1900-01-01", show_default=True, help=_FROM_DATE_HELP)
def topics_cmd(mode: str, batch_size: int, model: str, from_date: str) -> None:
    """LLM topic classification against the fixed taxonomy, over already-extracted
    narrative fields (nature_of_activities / political_activity_description /
    compensation_terms)."""
    conn = get_connection()
    llm_client = anthropic.Anthropic()
    try:
        summary = run_topics_stage(
            conn=conn, llm_client=llm_client, mode=mode, batch_size=batch_size, model=model, from_date=from_date
        )
    except anthropic.AuthenticationError as e:
        click.echo(f"Anthropic API authentication failed: {e}", err=True)
        raise SystemExit(1) from e
    finally:
        conn.close()
    click.echo(
        f"candidates={summary.candidates} processed={summary.processed} "
        f"topics_written={summary.topics_written} failed={summary.failed}"
    )


if __name__ == "__main__":
    main()
