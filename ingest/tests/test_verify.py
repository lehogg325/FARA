from __future__ import annotations

import pytest

from fara_ingest.manifest import Manifest
from fara_ingest.sources.fara.poll import PollResult
from fara_ingest.sources.fara.verify import VerificationFailed, verify_registrant_counts


def _seed_verified_registrants(manifest: Manifest, snapshot_date: str, row_count: int) -> None:
    manifest.start("fara", "registrants", snapshot_date)
    manifest.mark_verified(
        "fara",
        "registrants",
        snapshot_date,
        archive_key="k",
        sha256="abc",
        byte_size=1,
        row_count=row_count,
        http_status=200,
    )


def test_matching_counts_pass(tmp_path):
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    _seed_verified_registrants(manifest, "2026-08-21", row_count=7076)

    poll_result = PollResult(active_count=536, terminated_count=6540)
    result = verify_registrant_counts(manifest, "2026-08-21", poll_result)

    assert result.bulk_registrant_count == 7076
    assert result.poll_total == 7076
    assert result.difference == 0


def test_small_drift_within_tolerance_passes(tmp_path):
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    _seed_verified_registrants(manifest, "2026-08-21", row_count=7076)

    poll_result = PollResult(active_count=537, terminated_count=6540)  # +1 registrant since bulk pull
    result = verify_registrant_counts(manifest, "2026-08-21", poll_result, tolerance=2)

    assert result.difference == 1


def test_large_drift_fails_loudly(tmp_path):
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    _seed_verified_registrants(manifest, "2026-08-21", row_count=7076)

    poll_result = PollResult(active_count=100, terminated_count=100)  # obviously a truncated/corrupt case
    with pytest.raises(VerificationFailed):
        verify_registrant_counts(manifest, "2026-08-21", poll_result, tolerance=2)


def test_missing_bulk_snapshot_fails_loudly(tmp_path):
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    poll_result = PollResult(active_count=536, terminated_count=6540)

    with pytest.raises(VerificationFailed):
        verify_registrant_counts(manifest, "2026-08-21", poll_result)
