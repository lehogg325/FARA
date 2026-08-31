from __future__ import annotations

from dataclasses import dataclass

from fara_ingest.manifest import Manifest
from fara_ingest.sources.fara.constants import JURISDICTION
from fara_ingest.sources.fara.poll import PollResult


class VerificationFailed(RuntimeError):
    pass


@dataclass
class VerifyResult:
    bulk_registrant_count: int
    poll_active_count: int
    poll_terminated_count: int
    poll_total: int
    difference: int
    tolerance: int


def verify_registrant_counts(
    manifest: Manifest,
    snapshot_date: str,
    poll_result: PollResult,
    *,
    tolerance: int = 2,
) -> VerifyResult:
    """Cross-checks the day's bulk registrant count against a live JSON poll's
    Active+Terminated total. These two paths should be essentially synchronous
    (unlike the multi-day filing-publication lag), so any drift beyond a small
    tolerance means a truncated/corrupt bulk download, not real-world churn —
    fail loudly rather than silently proceeding.
    """
    bulk_count = manifest.get_verified_row_count(JURISDICTION, "registrants", snapshot_date)
    if bulk_count is None:
        raise VerificationFailed(
            f"no verified 'registrants' bulk download found for snapshot_date={snapshot_date}"
        )

    poll_total = poll_result.active_count + poll_result.terminated_count
    difference = abs(bulk_count - poll_total)
    if difference > tolerance:
        raise VerificationFailed(
            f"registrant count mismatch: bulk={bulk_count} poll(active+terminated)={poll_total} "
            f"(diff={difference} exceeds tolerance={tolerance})"
        )

    return VerifyResult(
        bulk_registrant_count=bulk_count,
        poll_active_count=poll_result.active_count,
        poll_terminated_count=poll_result.terminated_count,
        poll_total=poll_total,
        difference=difference,
        tolerance=tolerance,
    )
