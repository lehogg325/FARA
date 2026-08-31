from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fara_ingest.archive import RawArchive
from fara_ingest.sources.fara.client import RateLimitedClient

REGISTRANTS_ACTIVE_URL = "https://efile.fara.gov/api/v1/Registrants/json/Active"
REGISTRANTS_TERMINATED_URL = "https://efile.fara.gov/api/v1/Registrants/json/Terminated"


@dataclass
class PollResult:
    active_count: int
    terminated_count: int
    active_registration_numbers: set[int] = field(default_factory=set)
    terminated_registration_numbers: set[int] = field(default_factory=set)


def _extract_rows(payload: dict, wrapper_key: str) -> list[dict]:
    return payload.get(wrapper_key, {}).get("ROW", [])


def _registration_numbers(rows: list[dict]) -> set[int]:
    # .get(), never direct indexing: confirmed live that some rows are missing
    # expected keys entirely (docs/api-notes.md's Zip-key finding applies broadly
    # to this API — defend the same way for every field, not just Zip).
    return {r["Registration_Number"] for r in rows if "Registration_Number" in r}


def poll_registrants(
    *, archive: RawArchive, client: RateLimitedClient, when: datetime | None = None
) -> PollResult:
    """Purely diagnostic: archives raw JSON verbatim but never loads it into
    Postgres. Its only job is diffing registration numbers against what's
    currently loaded, to flag new registrants intraday between daily bulk
    refreshes (see plan: Ingest layer).
    """
    when = when or datetime.now(timezone.utc)
    date_str = when.date().isoformat()
    time_str = when.strftime("%H%M%SZ")

    active_payload = client.get_json(REGISTRANTS_ACTIVE_URL)
    archive.write_atomic(
        f"fara/json_polls/active/date={date_str}/poll_{time_str}.json",
        json.dumps(active_payload).encode("utf-8"),
    )

    terminated_payload = client.get_json(REGISTRANTS_TERMINATED_URL)
    archive.write_atomic(
        f"fara/json_polls/terminated/date={date_str}/poll_{time_str}.json",
        json.dumps(terminated_payload).encode("utf-8"),
    )

    active_rows = _extract_rows(active_payload, "REGISTRANTS_ACTIVE")
    terminated_rows = _extract_rows(terminated_payload, "REGISTRANTS_TERMINATED")

    return PollResult(
        active_count=len(active_rows),
        terminated_count=len(terminated_rows),
        active_registration_numbers=_registration_numbers(active_rows),
        terminated_registration_numbers=_registration_numbers(terminated_rows),
    )
