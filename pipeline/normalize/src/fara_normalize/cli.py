from __future__ import annotations

import click

from fara_normalize.db import get_connection
from fara_normalize.load import NoVerifiedArchiveError, load_dataset
from fara_normalize.load_dimensions import load_countries, load_document_types, load_jurisdictions
from fara_normalize.migrate import migrate


@click.group()
def main() -> None:
    """FARA normalize CLI."""


@main.command(name="migrate")
def migrate_cmd() -> None:
    """Apply pending schema migrations."""
    conn = get_connection()
    try:
        applied = migrate(conn)
    finally:
        conn.close()
    click.echo("Applied: " + ", ".join(applied) if applied else "No pending migrations.")


@main.command(name="load-dimensions")
def load_dimensions_cmd() -> None:
    """Seed jurisdictions, document_types, and countries reference tables."""
    conn = get_connection()
    try:
        j = load_jurisdictions(conn)
        d = load_document_types(conn)
        c = load_countries(conn)
        conn.commit()
    finally:
        conn.close()
    click.echo(f"jurisdictions={j} document_types={d} countries={c}")


@main.command(name="load")
@click.option("--dataset", required=True, help="Dataset to load, e.g. registrants.")
@click.option("--snapshot-date", default=None, help="Defaults to today.")
def load_cmd(dataset: str, snapshot_date: str | None) -> None:
    """Normalize a verified bulk archive into Postgres."""
    try:
        result = load_dataset(dataset, snapshot_date=snapshot_date)
    except NoVerifiedArchiveError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e
    click.echo(f"{dataset}: {result}")


if __name__ == "__main__":
    main()
