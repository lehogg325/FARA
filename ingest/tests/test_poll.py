from __future__ import annotations

from datetime import datetime, timezone

import httpx
import respx

from fara_ingest.archive import LocalArchive
from fara_ingest.sources.fara.client import RateLimitedClient
from fara_ingest.sources.fara.poll import (
    REGISTRANTS_ACTIVE_URL,
    REGISTRANTS_TERMINATED_URL,
    poll_registrants,
)

ACTIVE_PAYLOAD = {
    "REGISTRANTS_ACTIVE": {
        "ROW": [
            {"Registration_Number": 1, "Name": "A", "Zip": "07103"},
            {"Registration_Number": 2, "Name": "B", "Zip": 35243},
            {"Name": "C missing regnum"},  # confirmed-real shape: some rows omit keys entirely
        ]
    }
}
TERMINATED_PAYLOAD = {
    "REGISTRANTS_TERMINATED": {
        "ROW": [
            {"Registration_Number": 3, "Name": "D"},
        ]
    }
}


@respx.mock
def test_poll_registrants_counts_and_archives_verbatim(tmp_path):
    respx.get(REGISTRANTS_ACTIVE_URL).mock(return_value=httpx.Response(200, json=ACTIVE_PAYLOAD))
    respx.get(REGISTRANTS_TERMINATED_URL).mock(return_value=httpx.Response(200, json=TERMINATED_PAYLOAD))

    archive = LocalArchive(tmp_path / "raw")
    client = RateLimitedClient()
    try:
        result = poll_registrants(
            archive=archive, client=client, when=datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
        )
    finally:
        client.close()

    assert result.active_count == 3
    assert result.terminated_count == 1
    assert result.active_registration_numbers == {1, 2}  # the key-less row is excluded, not crashed on
    assert result.terminated_registration_numbers == {3}

    assert archive.exists("fara/json_polls/active/date=2026-08-21/poll_120000Z.json")
    assert archive.exists("fara/json_polls/terminated/date=2026-08-21/poll_120000Z.json")
